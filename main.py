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
"""

import base64
import os

from dotenv import find_dotenv, load_dotenv
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from smolagents import CodeAgent, tool
from typing import Literal

from src.config import LANGUAGE_MODELS
from src.tools import TOOLS, web_search, query_ifcopenshell_documentation

# Load secrets
load_dotenv(find_dotenv())

# %% Section::config


# Select LLM
model = LANGUAGE_MODELS["llama4_maverick"]

# Q&A
QUESTION = "What is the height of the ceiling in room A203?"
GROUND_TRUTH = "The height of the ceiling in room A203 is 2.58 m."

# Tracing
TRACING: Literal["phoenix", "langfuse"] = "langfuse"

if TRACING == "phoenix":
    from phoenix.otel import register
    from openinference.instrumentation.smolagents import SmolagentsInstrumentor

    register()
    SmolagentsInstrumentor().instrument()

elif TRACING == "langfuse":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry import trace

    LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
    LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]
    LANGFUSE_HOST = os.environ["LANGFUSE_HOST"]

    # Set up Langfuse
    LANGFUSE_AUTH = base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()
    ).decode()
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
        "https://cloud.langfuse.com/api/public/otel"  # EU data region
    )
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"
    os.environ["OTEL_PYTHON_LOG_LEVEL"] = "DEBUG"

    trace_provider = TracerProvider()
    trace_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    SmolagentsInstrumentor().instrument(
        tracer_provider=trace_provider, capture_llm_calls=True, capture_tool_calls=True
    )


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
)

# %% Section::run
agent.run(
    task=TASK_ORCHESTRATOR,
    max_steps=30,
    additional_args={
        "path_to_ifc_file": "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/bim_models/duplex/arc.ifc",
        "question_id": 1,
        "question": QUESTION,
    },
)

# TODO: use the additional_arg argument when calling agent.run() to pass more information (like model path, etc.)

# # %%
# from smolagents import GradioUI

# GradioUI(agent).launch()
# # %%
