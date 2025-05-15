# %% Section::setup
"""
Current implementation of the IfcAnswerEngineV3.
Trace can be seen on: https://cloud.langfuse.com/
"""

import base64
import os

from dotenv import find_dotenv, load_dotenv
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from smolagents import (CodeAgent, tool)

from src.config import LANGUAGE_MODELS
from src.tools import TOOLS

# Load secrets
load_dotenv(find_dotenv())

LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]
LANGFUSE_HOST = os.environ["LANGFUSE_HOST"]

# Set up Langfuse
LANGFUSE_AUTH=base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://cloud.langfuse.com/api/public/otel" # EU data region
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

# Set up Telemetry
trace_provider = TracerProvider()
trace_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
SmolagentsInstrumentor().instrument(tracer_provider=trace_provider)

# Select LLM
model = LANGUAGE_MODELS["llama4_maverick"]
# model = LANGUAGE_MODELS["llama4_scout"]

# %% Section::variables
QUESTION = "What is the height of the ceiling in room A203?"
GROUND_TRUTH = "The height of the ceiling in room A203 is 2.58 m."

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
    tools=[],
    model=model,
    name="answer_verifier",
    description="Compare your answer with the correct answer to verify that it is correct. If it is incorrect, explain why."
)

# %% Section - Orchestrator agent
TASK_ORCHESTRATOR = """
Your task is to assess if you can answer the question using the existing tools and, if not, define the requirements to create a new tool.

Here is how you should proceed:
    1. Try to answer the question using a combination of the existing tools (as well as some code in between if useful)
    2. If you are missing a tool to answer this question, you can call the tool_maker, who will give you a code snippet for the new tool.
    3. Once you have all the tools you need, and you think you can answer the question, call the verify_answer agent. This agent has access to the ground truth, and will tell you if your answer is correct.
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
    max_print_outputs_length=2**12 # 4.096
)

# Define task
# # GFA
# task = "What is the total gross floor area of the building? Carefully review the definition of the GFA first, to be sure what areas need to be included or excluded in this calculation. Based on a rough calculation with an IFC viewer, it should be around 313 m² (156 m² per story, 2 stories)"

# Room names + create tool at the end
task = "Give me the name of all the rooms in the building, as well as a helper function that would enable me to get this information directly for another model next time."

# Run the agent
agent.run(
    task=task,
    max_steps=30,
    additional_args={
        "path_to_ifc_file": "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/bim_models/duplex/arc.ifc"
    }
)

# TODO: use the additional_arg argument when calling agent.run() to pass more information (like model path, etc.)

# # %%
# from smolagents import GradioUI

# GradioUI(agent).launch()
# # %%
