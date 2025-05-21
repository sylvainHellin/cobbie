"""Import all available tools"""


# Import all functions from each file
def load_tools(tools: list) -> list:
    import os
    import importlib
    import inspect
    from smolagents import Tool

    # Get the directory containing this __init__.py file
    tools_dir = os.path.dirname(__file__)

    # Get all Python files in the directory (excluding __init__.py)
    python_files = [
        f[:-3]
        for f in os.listdir(tools_dir)
        if f.endswith(".py") and f != "__init__.py"
    ]

    for module_name in python_files:
        module = importlib.import_module(f".{module_name}", package=__package__)
        # Get all objects from the module
        for name, obj in inspect.getmembers(module):
            # Check if the object is a Tool instance (from @tool decorator)
            if isinstance(obj, Tool):
                # Add to global namespace and tools list
                globals()[name] = obj
                tools.append(obj)
            # Add other functions to global namespace anyway
            elif inspect.isfunction(obj):
                globals()[obj.__name__] = obj

    return tools


TOOLS = load_tools(tools=[])

# Clean up temporary variables
del load_tools
