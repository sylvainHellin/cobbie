# %%
def main():
    from smolagents import CodeAgent
    from src.tools import TOOLS
    from src.config import LANGUAGE_MODELS

    model = LANGUAGE_MODELS["claude"]

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
    )

    agent.run(
        "What is the height of the ceiling in room A203? Path to the .ifc file: /Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/bim_models/duplex/arc.ifc"
    )


if __name__ == "__main__":
    main()

# %%

# %%

# %%

# %%

# %%
