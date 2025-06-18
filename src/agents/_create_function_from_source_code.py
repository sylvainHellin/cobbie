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

from ._extract_function_metadata import _extract_function_metadata


def _create_function_from_source_code(
    code: str,
    function_name: str,
    imports: Optional[Dict[str, Any]] = None,
    merge_with_defaults: bool = True,
) -> Callable:
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
                    return f"Error executing {function_name}: {str(e)}"

            # Copy the signature from the original function to the wrapper
            tool_wrapper.__signature__ = sig
            return tool_wrapper

        tool_wrapper = create_dynamic_wrapper()

        # Set the function name and docstring for the tool
        tool_wrapper.__name__ = function_name

        # Create a more descriptive docstring for DSPy using extracted metadata
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
                return_description = "Return type not documented - preserves function's original return type"
        else:
            return_description = (
                "Return type not specified - preserves function's original return type"
            )

        tool_wrapper.__doc__ = f"""
        {metadata.docstring or f"Tool: {function_name}"}
        
        Args:
{args_description}
            
        Returns:
            {return_description}
        """

        return tool_wrapper

    except Exception as e:
        # Return a dummy function that reports the error
        error_message = str(e)

        def error_tool(*args, **kwargs) -> str:
            return f"Error creating tool {function_name}: {error_message}"

        error_tool.__name__ = function_name
        error_tool.__doc__ = f"Error in function {function_name}"
        return error_tool


if __name__ == "__main__":
    wrong_code = """
    import math

    def sqrt(number: int) -> int:
        '''
        Return the square root of a number
        '''
        return math.sqrt(4)
    """
    code = """
    def sqrt(number: int) -> int:
        '''
        Return the square root of a number
        '''
        import math
        return math.sqrt(number)
"""

    # Example with custom imports
    custom_code = """
    import os
    import datetime

    def get_info() -> str:
        '''
        Get system and time info
        '''
        return f"Current directory: {os.getcwd()}, Time: {datetime.datetime.now()}"
    """

    function_name = "sqrt"

    # Test the original code with default imports
    print("1. Testing code with import inside function (default imports):")
    new_tool = _create_function_from_source_code(code=code, function_name=function_name)
    res = new_tool(9)
    print(f"Square root of 9 is: {res}")

    # Test the wrong_code with default imports
    print("\n2. Testing code with import at module level (default imports):")
    new_tool_wrong = _create_function_from_source_code(
        code=wrong_code, function_name=function_name
    )
    res_wrong = new_tool_wrong(4)
    print(f"Result: {res_wrong}")

    # Test with custom imports (merging with defaults)
    print("\n3. Testing with custom imports (merged with defaults):")
    import datetime
    import os

    custom_imports = {"os": os, "datetime": datetime}
    custom_tool = _create_function_from_source_code(
        code=custom_code,
        function_name="get_info",
        imports=custom_imports,
        merge_with_defaults=True,
    )
    custom_res = custom_tool()
    print(f"Result: {custom_res}")

    # Test with only custom imports (no defaults)
    print("\n4. Testing with only custom imports (no defaults):")
    minimal_imports = {"math": math}
    minimal_tool = _create_function_from_source_code(
        code=wrong_code,
        function_name=function_name,
        imports=minimal_imports,
        merge_with_defaults=False,
    )
    minimal_res = minimal_tool(4)
    print(f"Result: {minimal_res}")

    # Test with empty imports (will fail because math is not available)
    print("\n5. Testing with empty imports (should fail):")
    empty_tool = _create_function_from_source_code(
        code=wrong_code,
        function_name=function_name,
        imports={},
        merge_with_defaults=False,
    )
    empty_res = empty_tool(4)
    print(f"Result: {empty_res}")

    # Test submodule imports
    print("\n6. Testing submodule imports:")
    submodule_code = """
    import ifcopenshell.util.element

    def test_submodules() -> str:
        '''
        Test if submodule imports work
        '''
        # Test if we can access the submodule
        try:
            # Just check if the module exists
            module_name = ifcopenshell.util.element.__name__
            return f"Success: {module_name}"
        except Exception as e:
            return f"Error accessing submodules: {e}"
    """

    submodule_tool = _create_function_from_source_code(
        code=submodule_code, function_name="test_submodules"
    )
    submodule_res = submodule_tool()
    print(f"Result: {submodule_res}")

    # Also test with os submodule (which should work)
    print("\n7. Testing os.path submodule:")
    os_submodule_code = """
    import os.path

    def test_os_path() -> str:
        '''
        Test if os.path submodule works
        '''
        try:
            return f"Success: {os.path.__name__}, exists function available: {hasattr(os.path, 'exists')}"
        except Exception as e:
            return f"Error: {e}"
    """

    import os

    os_tool = _create_function_from_source_code(
        code=os_submodule_code,
        function_name="test_os_path",
        imports={"os": os},
        merge_with_defaults=False,
    )
    os_res = os_tool()
    print(f"Result: {os_res}")

    # 8. Test with a real tool created by an LLM
    tool_code = '''def get_room_ceiling_height(ifc_file_path: str, room_identifier: str) -> dict:
        """
        Get the ceiling height of a room/space in an IFC model.

        Args:
            ifc_file_path (str): Path to the IFC file
            room_identifier (str or int): Room number, name, or ID

        Returns:
            dict: Dictionary containing:
                - height (float): Ceiling hweight value
                - unit (str): Unit of measurement
                - room_info (dict): Additional room information
                - success (bool): Whether the operation was successful
                - message (str): Informative message about the result
        """
        result = {
            "height": None,
            "unit": None,
            "room_info": {},
            "success": False,
            "message": "",
        }

        try:
            # Load the IFC file
            ifc_file = ifcopenshell.open(ifc_file_path)

            # Get units from the file
            units = ifc_file.by_type("IfcUnitAssignment")
            length_unit = "meter"  # Default unit
            if units:
                for unit in units[0].Units:
                    if unit.is_a("IfcSIUnit") and unit.UnitType == "LENGTHUNIT":
                        length_unit = unit.Name.lower()
                        if hasattr(unit, "Prefix") and unit.Prefix:
                            prefix_map = {
                                "MILLI": "milli",
                                "CENTI": "centi",
                                "DECI": "deci",
                                "KILO": "kilo",
                                "MEGA": "mega",
                            }
                            if unit.Prefix in prefix_map:
                                length_unit = f"{prefix_map[unit.Prefix]}{length_unit}"

            result["unit"] = length_unit

            # Find all spaces/rooms in the model
            spaces = ifc_file.by_type("IfcSpace")

            # Find the requested room
            target_room = None

            # Check if room_identifier is an integer (could be an ID)
            if isinstance(room_identifier, int) or (
                isinstance(room_identifier, str) and room_identifier.isdigit()
            ):
                room_id = int(room_identifier)
                try:
                    target_room = ifc_file.by_id(room_id)
                    if not target_room.is_a("IfcSpace"):
                        target_room = None  # Reset if the ID doesn't refer to a space/room
                except:
                    pass  # ID not found, continue with other search methods

            # If not found by ID, search by name or number
            if target_room is None:
                for space in spaces:
                    # Check various properties that might contain the identifier
                    space_name = space.Name if hasattr(space, "Name") else ""
                    space_long_name = space.LongName if hasattr(space, "LongName") else ""

                    # Also check property sets for room number
                    space_number = None
                    psets = ifcopenshell.util.element.get_psets(space)
                    for pset_name, properties in psets.items():
                        if "Number" in properties:
                            space_number = properties["Number"]

                    # Compare with the identifier
                    if (
                        (space_name and str(room_identifier) == space_name)
                        or (space_long_name and str(room_identifier) in space_long_name)
                        or (space_number and str(room_identifier) == space_number)
                    ):
                        target_room = space
                        break

            if target_room is None:
                result["message"] = f"Room '{room_identifier}' not found in the IFC model"
                return result

            # Room found, get its info
            result["room_info"] = {
                "id": target_room.id(),
                "name": target_room.Name if hasattr(target_room, "Name") else None,
                "long_name": target_room.LongName
                if hasattr(target_room, "LongName")
                else None,
            }

            # Get property sets for the room
            psets = ifcopenshell.util.element.get_psets(target_room)

            # Look for ceiling height in property sets
            height_value = None
            height_sources = []

            # Check in various property sets for height information
            # Revit dimensions usually contain this
            if "PSet_Revit_Dimensions" in psets:
                dims = psets["PSet_Revit_Dimensions"]
                if "Unbounded Height" in dims:
                    height_value = dims["Unbounded Height"]
                    height_sources.append("Unbounded Height from PSet_Revit_Dimensions")

            # Check in constraints (limit offset is often the height)
            if "PSet_Revit_Constraints" in psets and height_value is None:
                constraints = psets["PSet_Revit_Constraints"]
                if "Limit Offset" in constraints:
                    height_value = constraints["Limit Offset"]
                    height_sources.append("Limit Offset from PSet_Revit_Constraints")

            # If not found in those specific places, check all property sets
            if height_value is None:
                for pset_name, properties in psets.items():
                    for prop_name, prop_value in properties.items():
                        if "height" in prop_name.lower() and isinstance(
                            prop_value, (int, float)
                        ):
                            height_value = prop_value
                            height_sources.append(f"{prop_name} from {pset_name}")
                            break

            # If no height found in properties, try calculating from geometry
            if height_value is None and hasattr(target_room, "Representation"):
                # This would require additional geometry processing using ifcopenshell.geom
                # For simplicity, we're not implementing full geometric analysis here
                height_sources.append("Geometric calculation would be needed")

            # Update the result
            if height_value is not None:
                result["height"] = height_value
                result["success"] = True
                result["message"] = (
                    f"Room found and height determined from: {', '.join(height_sources)}"
                )
            else:
                result["message"] = (
                    "Room found but couldn't determine ceiling height from available properties"
                )

            return result

        except Exception as e:
            result["message"] = f"Error: {str(e)}"
            return result'''
    new_tool = _create_function_from_source_code(
        code=tool_code, function_name="get_room_ceiling_height"
    )

    result_real_tool = new_tool(
        ifc_file_path="src/bim_models/duplex/arc.ifc", room_identifier="A203"
    )
    print("\n8. Testing with a real tool created by an LLM: get_room_ceiling_height")
    print(f"Result: {result_real_tool}")
