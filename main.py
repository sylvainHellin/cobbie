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
    - Implement the verify_answer tool
    - Create a detailled summary of the structure of the ifcOpenShell API to be included as part of the context to the ToolMaker agent.
"""

import base64
import os
from datetime import datetime
from typing import Literal

import opentelemetry.trace
from dotenv import find_dotenv, load_dotenv
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from smolagents import CodeAgent, tool
from smolagents.agents import ActionStep
from smolagents.monitoring import LogLevel

from src.config import LANGUAGE_MODELS, ROOT_PATH
from src.db import (
    DatasetRow,
    LogRow,
    RunsRow,
    get_dataset_row,
    get_ifc_model_row,
    get_tokens_count_logs,
    insert_new_log,
    insert_new_run,
)
from src.tools import TOOLS
from src.special_tools import query_ifcopenshell_documentation, web_search

# Load secrets
load_dotenv(find_dotenv())

# %% Section::config
# Select LLM
llm_name = "llama4_maverick"
LLM = LANGUAGE_MODELS[llm_name]

# Select question
question_id = 1
dataset_row: DatasetRow = get_dataset_row(id=question_id)
question: str = dataset_row.question or ""
ground_truth: str = dataset_row.ground_truth or ""
# If no IFC_ID exist, there is a problem: process should interrupt
if dataset_row.ifc_id is None:
    exit()

# Configure path
ifc_model = get_ifc_model_row(id=dataset_row.ifc_id)
if ifc_model.model_path is None:
    exit()
ifc_path = os.path.join(ROOT_PATH, ifc_model.model_path)
ifc_description = ifc_model.model_description or "The IFC model of a building."

# Tracing - Phoenix or Langfuse for OTel, SQLite is always active via callback
TRACING: Literal["phoenix", "langfuse"] = "langfuse"

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


# Custom callback for logging each step of the agentic workflow
def log_step(
    step: ActionStep,
    agent: CodeAgent,
) -> None:
    global run_id

    previous_input_tokens, previous_output_tokens = get_tokens_count_logs(run_id=run_id)
    new_log = LogRow(
        agent_name=agent.name,
        run_id=run_id,
        step_number=step.step_number,
        timestamp=datetime.now(),
        model_output=step.model_output,
        action_input_code=None,  # TODO update this when the structure of the model output is clearer
        action_output=str(
            step.action_output
        ),  # TODO need to investigate why sub-agent are outputing a dict instead of a string
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
def get_correct_answer() -> str:
    """
    Return the ground truth to the question.
    """
    global ground_truth

    return ground_truth  # TODO update this to be more robust for eval pipeline


tool_maker = CodeAgent(
    tools=[web_search, query_ifcopenshell_documentation],
    model=LLM,
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
    step_callbacks=[log_step],
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
agent_orchestrator = CodeAgent(
    tools=TOOLS,
    model=LLM,
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
    managed_agents=[tool_maker],
    verbosity_level=LogLevel.DEBUG,
    step_callbacks=[log_step],
)

# %% Section::run
# Create a new run
current_run = RunsRow(question_id=question_id, llm=llm_name, timestamp=datetime.now())
run_id = insert_new_run(new_run=current_run)

agent_orchestrator.run(
    task=TASK_ORCHESTRATOR,
    additional_args={
        "ifc_model_path": ifc_path,
        "ifc_model_description": ifc_description,
        "question": question,
    },
)
