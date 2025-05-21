# %% Section::setup
"""
Current implementation of the IfcAnswerEngineV3.

Tracing:
    1. Phoenix
    If running tracing with phoenix, need to run the server locally first
    ```bash
    python -m phoenix.server.main serve
    ```

    Then the trace can be observed at `http://0.0.0.0:6006/projects/`

    2. LangFuse
    If running tracing with Langfuse, trace can be seen on: https://cloud.langfuse.com/

Backlog:
    - Create a detailled summary of the structure of the ifcOpenShell API to be included as part of the context to the ToolMaker agent.
    - Remove question_id from logs and move it into runs.
    - Implemment the logging of runs in the db
"""

import base64
import os
import re
import sqlite3
import uuid
from datetime import datetime
from sqlite3 import Connection
from typing import Literal

import opentelemetry.trace
from dotenv import find_dotenv, load_dotenv
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from smolagents import CodeAgent, tool
from smolagents.agents import ActionStep
from smolagents.monitoring import LogLevel

from src.config import LANGUAGE_MODELS
from src.db import (
    get_dataset_row,
    DatasetRow,
    RunsRow,
    LogRow,
    insert_new_run,
    insert_new_log,
    get_log_row,
    get_last_log_id,
    get_tokens_count_logs,
)
from src.tools import TOOLS, query_ifcopenshell_documentation, web_search

# Load secrets
load_dotenv(find_dotenv())

# %% Section::config

# Select LLM
model = LANGUAGE_MODELS["llama4_maverick"]

# Select question
QUESTION_ID = 1

# SQLite Database setup
current_run_id = None
dataset_row: DatasetRow = get_dataset_row(id=1)
QUESTION = dataset_row.question if dataset_row.question is not None else ""
GROUND_TRUTH = dataset_row.ground_truth if dataset_row.ground_truth is not None else ""

previous_agent_token_counts = {}  # To store previous token counts per agent for calculating per-step tokens TODO refactor

# Tracing - Phoenix or Langfuse for OTel, SQLite is always active via callback
TRACING: Literal["phoenix", "langfuse"] = "phoenix"

if TRACING == "phoenix":
    from phoenix.otel import register

    register()
    SmolagentsInstrumentor().instrument(capture_llm_calls=True, capture_tool_calls=True)
    print("Phoenix tracing enabled.")

elif TRACING == "langfuse":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
    LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]

    LANGFUSE_AUTH = base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()
    ).decode()
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
        "https://cloud.langfuse.com/api/public/otel"
    )
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

    trace_provider = TracerProvider()
    trace_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    opentelemetry.trace.set_tracer_provider(trace_provider)

    SmolagentsInstrumentor().instrument(
        tracer_provider=trace_provider, capture_llm_calls=True, capture_tool_calls=True
    )
    print("Langfuse tracing enabled.")


# Regex to extract code from the model_output (from smolagents.codes.CodeAgent.CODE_BLOCK_RE)
CODE_BLOCK_RE = re.compile(r"```(?:python|py)?\s*([\s\S]+?)\s*```")


# Custom callback for logging each step of the agentic workflow
def log_step(
    step: ActionStep,
    agent: CodeAgent,
    run_id: int,
) -> None:
    previous_input_tokens, previous_output_tokens = get_tokens_count_logs(run_id=run_id)
    new_log = LogRow(
        agent_name=agent.name,
        run_id=run_id,
        step_number=step.step_number,
        timestamp=datetime.now(),
        model_output=step.model_output,
        action_input_code=None,  # TODO update this when the structure of the model output is clearer
        action_output=step.action_output,
        observations=step.observations,
        error=str(step.error),
        duration=step.duration,
        input_tokens=agent.monitor.total_input_token_count - previous_input_tokens,
        output_tokens=agent.monitor.total_output_token_count - previous_output_tokens,
    )
    insert_new_log(new_log=new_log)

    return None


# %% Section::Managed agents
# %% Subsection::answer_verifier


# tools
@tool
def get_correct_answer(question_id: int) -> str:
    """
    Query the database and return the ground truth to the given question

    Args:
        question_id: The ID of the question for which the ground truth is to be returned.

    Returns:
        str: the correct answer
    """
    return GROUND_TRUTH


answer_verifier = CodeAgent(
    tools=[get_correct_answer],
    model=model,
    name="answer_verifier",
    description="Check your answer to see if it is correct.",
    verbosity_level=LogLevel.DEBUG,
    step_callbacks=[log_step],
)

tool_maker = CodeAgent(
    tools=[web_search, query_ifcopenshell_documentation],
    model=model,
    name="tool_maker",
    description="Generate a new tool based on the requirements provided. Test the new tool and return a code snippet of the tool implementation if it works.",
    additional_authorized_imports=[
        "ifcopenshell",
        "ifcopenshell.util.element",
        "ifcopenshell.util.shape",
        "ifcopenshell.util.placement",
        "ifcopenshell.util.geolocation",
        "ifcopenshell.util.system",
        "ifcopenshell.geom",
        "ifcopenshell.file",
        "ifcopenshell.entity_instance",
    ],
    max_print_outputs_length=2**12,  # 4.096
    verbosity_level=LogLevel.DEBUG,
    step_callbacks=[sqlite_log_callback],
)

# %% Section::Orchestrator agent
TASK_ORCHESTRATOR = """
Your task is to assess if you can answer the question using the existing tools and, if not, define the requirements to create a new tool.

Here is how you should proceed:
    1. Try to answer the question using a combination of the existing tools (as well as some code in between if useful)
    2. If you are missing a tool to answer this question, you can call the tool_maker, who will give you a code snippet for the new tool.
    3. Once you have all the tools you need, and you think you can answer the question, call the `answer_verifier` agent. This agent has access to the ground truth, and will tell you if your answer is correct.You MUST call him BEFORE answering the question with the `final_answer` tool.
        3.1 If the answer is correct, call the save_tool agent who will review the code snippet of the new tool, ensure it's format is compliant, and save it for future use.
        3.2 If the answer is incorrect, use the provided feedback to try to come to the right answer. If you think the error comes from the new tool, you can call the tool_maker again and ask him to fix it.
"""

# Set up the agent
agent = CodeAgent(
    tools=TOOLS,
    model=model,
    name="agent_orchestrator",
    additional_authorized_imports=[
        "ifcopenshell",
        "ifcopenshell.util.element",
        "ifcopenshell.util.shape",
        "ifcopenshell.util.placement",
        "ifcopenshell.util.geolocation",
        "ifcopenshell.util.system",
        "ifcopenshell.geom",
        "ifcopenshell.file",
        "ifcopenshell.entity_instance",
    ],
    max_print_outputs_length=2**12,  # 4.096
    managed_agents=[answer_verifier, tool_maker],
    verbosity_level=LogLevel.DEBUG,
    step_callbacks=[sqlite_log_callback],
)

# %% Section::run

# Generate a unique run ID for this execution


# TODO: use the additional_arg argument when calling agent.run() to pass more information (like model path, etc.)

# # %%

# from smolagents import GradioUI

# GradioUI(agent).launch()
# # %%
