# Pre-import common modules that might be needed in generated code
import math
import textwrap
from typing import Any, Callable, Dict, Optional

import ifcopenshell
import ifcopenshell.entity_instance
import ifcopenshell.file
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.geolocation
import ifcopenshell.util.placement
import ifcopenshell.util.shape
import ifcopenshell.util.system
import numpy
import pandas

from src.schemas import Result, ok, err
from ._extract_function_metadata import _extract_function_metadata


def _create_function_from_source_code(
    code: str,
    function_name: str,
    imports: Optional[Dict[str, Any]] = None,
    merge_with_defaults: bool = True,
) -> Result[Callable, str]:
    """
    Create a callable tool from the generated code that can be used by the assessor.
    The tool executes the function in isolation without exposing implementation details.

    Args:
        code: The source code containing the function to create
        function_name: The name of the function to extract from the code
        imports: Optional dictionary of modules to make available in the global scope.
                Keys are module names, values are the imported modules.
        merge_with_defaults: If True, merge provided imports with default imports.
                           If False, use only the provided imports (plus __builtins__).

    Returns:
        Result[Callable, str]: Ok(function) on success, Err(error_message) on failure.
                              Use .is_ok() and .is_err() to check the result status.
    """
    # Clean up the code string - remove common leading whitespace
    cleaned_code = textwrap.dedent(code).strip()

    # Prepare default imports
    default_imports = {
        "ifcopenshell": ifcopenshell,
        "ifcopenshell.util.element": ifcopenshell.util.element,
        "ifcopenshell.util.shape": ifcopenshell.util.shape,
        "ifcopenshell.util.placement": ifcopenshell.util.placement,
        "ifcopenshell.util.geolocation": ifcopenshell.util.geolocation,
        "ifcopenshell.util.system": ifcopenshell.util.system,
        "ifcopenshell.geom": ifcopenshell.geom,
        "ifcopenshell.file": ifcopenshell.file,
        "ifcopenshell.entity_instance": ifcopenshell.entity_instance,
        "math": math,
        "numpy": numpy,
        "pandas": pandas,
    }

    # Determine which imports to use
    if imports is None:
        final_imports = default_imports
    elif merge_with_defaults:
        final_imports = {**default_imports, **imports}  # imports override defaults
    else:
        final_imports = imports

    # Execute the code to create the function
    global_scope = {"__builtins__": __builtins__, **final_imports}
    local_scope = {}

    try:
        exec(cleaned_code, global_scope, local_scope)
        generated_function = local_scope.get(function_name)

        if not generated_function:
            raise ValueError(f"Function {function_name} not found in generated code")

        # Extract function metadata to get the signature
        metadata = _extract_function_metadata(cleaned_code, function_name)

        # Create a dynamic wrapper that matches the original function signature
        def create_dynamic_wrapper():
            import inspect

            sig = inspect.signature(generated_function)

            # Create wrapper function dynamically with the same signature
            def tool_wrapper(*args, **kwargs):
                """Dynamic tool wrapper for generated function that preserves return type."""
                try:
                    result = generated_function(*args, **kwargs)
                    return result  # Return the actual result, don't convert to string
                except Exception as e:
                    return f"Error processing the function with the `tool_wrapper` {function_name}: {str(e)}"

            # Copy the signature from the original function to the wrapper
            tool_wrapper.__signature__ = sig  # type: ignore
            return tool_wrapper

        tool_wrapper = create_dynamic_wrapper()

        # Set the function name and docstring for the tool
        tool_wrapper.__name__ = function_name

        # Create a more descriptive docstring
        args_description = ""
        if metadata.args:
            args_list = []
            for i, arg in enumerate(metadata.args):
                # Check if this argument has a default value
                default_index = i - (len(metadata.args) - len(metadata.defaults))
                if default_index >= 0 and default_index < len(metadata.defaults):
                    default_val = metadata.defaults[default_index]
                    args_list.append(
                        f"            {arg}: Parameter with default value {default_val}"
                    )
                else:
                    args_list.append(f"            {arg}: Required parameter")
            args_description = "\n".join(args_list)

        # Create intelligent return type description
        return_description = "The actual return value of the function"
        if metadata.return_type:
            return_description = (
                f"{metadata.return_type}: As specified in the function signature"
            )
        elif metadata.docstring:
            # Try to extract return info from docstring more intelligently
            docstring_lines = metadata.docstring.split("\n")
            returns_found = False
            for i, line in enumerate(docstring_lines):
                line_stripped = line.strip()
                line_lower = line_stripped.lower()

                # Look for "Returns:" section
                if line_lower.startswith("returns:"):
                    returns_found = True
                    # Get the description from this line if it exists
                    if (
                        ":" in line_stripped
                        and len(line_stripped.split(":", 1)[1].strip()) > 0
                    ):
                        return_description = line_stripped.split(":", 1)[1].strip()
                        break
                    # Otherwise, look for description in next non-empty lines
                    elif i + 1 < len(docstring_lines):
                        for j in range(i + 1, len(docstring_lines)):
                            next_line = docstring_lines[j].strip()
                            if next_line and not next_line.lower().startswith(
                                ("args:", "parameters:", "raises:", "examples:")
                            ):
                                return_description = next_line
                                break
                    break

            # If no "Returns:" found, use a generic description
            if not returns_found:
                return_description = "Return type not specified."
        else:
            return_description = "Return type not specified."

        tool_wrapper.__doc__ = f"""
        {metadata.docstring or f"Tool: {function_name}"}

        Args:
            {args_description}

        Returns:
            {return_description}
        """

        return ok(tool_wrapper)

    except Exception as e:
        # Return error result instead of dummy function
        error_message = str(e)
        return err(error_message)


if __name__ == "__main__":
    # Import here to avoid circular imports in main execution
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

    python_code = '''import ifcopenshell
import ifcopenshell.util.element
from typing import List

def get_emergency_exit_doors(path_ifc_model: str):
    """
    Retrieves a list of IfcDoor entities that are designated as emergency exits.

    Args:
    path_ifc_model (str): Path to the IFC file.

    Returns:
    List[ifcopenshell.entity_instance.entity_instance]: A list of IfcDoor entities representing emergency exits.
    """
    # Load the IFC file from the provided path
    ifc_file = ifcopenshell.open(path_ifc_model)

    # Retrieve all IfcDoor entities
    doors = ifc_file.by_type('IfcDoor')

    # Initialize an empty list to store emergency exit doors
    emergency_exit_doors = []

    # Iterate through each IfcDoor entity
    for door in doors:
        # Check if the door has a property set that indicates it's an emergency exit
        psets = ifcopenshell.util.element.get_psets(door)
        for pset_name, properties in psets.items():
            if 'EmergencyExit' in pset_name or 'emergencyexit' in (prop.lower() for prop in properties):
                emergency_exit_doors.append(door)
                break

    return emergency_exit_doors'''
    from src.config import TEST_IFC_PATH

    function_name = "get_emergency_exit_doors"
    creation_result = _create_function_from_source_code(
        function_name="get_emergency_exit_doors", code=python_code
    )

    if creation_result.is_ok():
        print(f"✓ Successfully created function: {function_name}")
        get_emergency_exit_doors = creation_result.unwrap()
        result = get_emergency_exit_doors(TEST_IFC_PATH)
        print(f"---\nResult of function {function_name}:\n{result}\n")
        print(
            f"docstring of function: {function_name}:\n {get_emergency_exit_doors.__doc__}"
        )
        print("test completed")
    else:
        print(f"✗ Failed to create function: {creation_result.unwrap_err()}")
        print("test failed")
