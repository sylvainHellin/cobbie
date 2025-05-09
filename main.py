# %%

from smolagents import CodeAgent
from src.tools import TOOLS
from src.config import LANGUAGE_MODELS
from phoenix.otel import register
from openinference.instrumentation.smolagents import SmolagentsInstrumentor

# set up tracing
register()
SmolagentsInstrumentor().instrument()

# Select LLM
model = LANGUAGE_MODELS["claude"]

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
