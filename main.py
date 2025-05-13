# %%
'''
Current implementation of the IfcAnswerEngineV3.
Trace can be seen on: https://cloud.langfuse.com/
'''

import base64
import os

from dotenv import find_dotenv, load_dotenv
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from smolagents import CodeAgent

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
model = LANGUAGE_MODELS["llama4_scout"]

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
