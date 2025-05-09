# %%

from smolagents import CodeAgent
from src.tools import TOOLS
from src.config import LANGUAGE_MODELS

model = LANGUAGE_MODELS["mistral"]

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
    max_print_outputs_length=2048
)

agent.run(
    "What is the height of the ceiling in room A203?",
    max_steps=20,
    additional_args={
        "path_to_ifc_file": "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/bim_models/duplex/arc.ifc"
    }
)
# TODO: use the additional_arg argument when calling agent.run() to pass more information (like model path, etc.)

# # %%
# from smolagents import GradioUI

# GradioUI(agent).launch()
# # %%
