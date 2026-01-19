// ToolFixer - Analyzes and fixes faulty helper functions using iterative CodeAct pattern
// This agent examines identified faulty functions and provides corrected implementations through iteration

function HelperFunctionDebugger(
  faulty_function_name: string @description("Name of the identified faulty function"),
  faulty_function_implementation: string @description("Current (faulty) implementation of the function that needs to be fixed"),
  history_faulty_tool_use: string? @description(#"
    The full trace of thoughts, code and result of Cobbie, where the faulty helper function was used.
  "#),
  error_description: string @description("Detailed description of what's wrong with the function and test cases showing the failure"),
  ifc_model_path: string @description("Path to the IFC model where the failure occurred for testing purposes"),
  other_bim_models_for_testing: string[]? @description("List of paths to other available BIM models for testing generalization. If not provided, the system will automatically discover other IFC files in the bim_models directory."),
  previous_attempts: string? @description("Previous code execution results and attempts, if any")
) -> CodeAction | UpdatedHelperFunction {
  client GLM_4_7
  prompt #"
    You are an expert Python developer and software architect specializing in BIM (Building Information Modeling) systems.

    Your task is to iteratively analyze and fix a FAULTY helper function. You can write Python code to test, debug, and validate your fixes before providing the final implementation.

    AVAILABLE TOOL FOR DEBUGGING:

    You have access to the following tool in your Python code execution environment:

    **query_ifcopenshell_docs(query: str, max_tokens: int = 2048) -> str**

    Retrieves up-to-date documentation and code examples from the IFCOpenShell library documentation.

    Parameters:
      - query (str): The topic or query to focus the documentation on (e.g., "file reading",
                     "geometry", "IFC entities", "relationship traversal")
      - max_tokens (int): Maximum number of tokens to retrieve (default: 2048, can be increased for more context)

    Returns:
      - str: The documentation text with relevant information and code examples

    Usage Example:
    ```python
    # Query documentation about spatial relationships
    docs = query_ifcopenshell_docs(
        "How to find which building storey an IfcDoor belongs to using spatial containment relationships",
        max_tokens=1024
    )
    print(docs)

    # Query documentation about opening IFC files
    docs = query_ifcopenshell_docs("opening IFC files and reading entities")
    print(docs)
    ```

    CRITICAL: When debugging functions that use ifcopenshell, ALWAYS use the query_ifcopenshell_docs tool to verify correct API usage.
    Never rely on your knowledge of this library—you are not familiar with it and the API may have changed.
    You can execute code to test your implementation and query documentation simultaneously in the same iteration.

    FAULTY FUNCTION ANALYSIS:

    Function Name: {{ faulty_function_name }}

    Current (Faulty) Implementation:
    ```python
    {{ faulty_function_implementation }}
    ```

    Error Description:
    {{ error_description }}

    {% if history_faulty_tool_use %}
    HISTORY OF THE FAULTY TOO USE:
    {{ history_faulty_tool_use }}

    {% endif %}
    IFC Model Path: {{ ifc_model_path }}

    {% if other_bim_models_for_testing %}
    OTHER BIM MODELS PATH FOR TESTING:
    {{ other_bim_models_for_testing | join(", ") }}

    {% endif %}
    {% if previous_attempts %}
    PREVIOUS ATTEMPTS:
    {{ previous_attempts }}

    Learn from previous attempts and iterate to improve the fix.
    {% endif %}

    YOUR ITERATIVE FIXING TASK:

    1. **Analyze the Issues**: Understand exactly what's wrong with the current implementation
    2. **Develop a Fix Strategy**: Plan how to address the identified issues
    3. **Write and Test Code**: Use Python code to implement and test your fixes
    4. **Validate Results**: Test against the error scenarios to ensure the fix works
    5. **Iterate**: Continue refining until the fix is robust and correct
    6. **Provide Final Implementation**: Only provide UpdatedHelperFunction when thoroughly tested

    COMMON TYPES OF ISSUES TO LOOK FOR:

    1. **Logic Errors**: Incorrect algorithms, wrong conditions, flawed reasoning
    2. **Parameter Handling**: Ignoring function parameters, wrong parameter usage
    3. **Data Filtering**: Not properly filtering data based on criteria (e.g., ignoring floor_name parameter)
    4. **Edge Cases**: Failing on specific inputs, not handling error cases
    5. **IFC API Usage**: Incorrect use of ifcopenshell functions and properties
    6. **Return Value Issues**: Returning wrong type or incorrect data
    7. **Scope Errors**: Including too much or too little data in results

    TESTING STRATEGY:

    You MUST test your fixes using the provided IFC model:
    - Test the original failing scenario from the error description
    - Test edge cases to ensure robustness
    - Verify the function returns the correct types and values
    - Compare against expected results from the error description

    FIXING GUIDELINES:

    1. **Preserve Function Signature**: Keep the same function name and parameters
    2. **Maintain Docstring**: Update docstring if needed, but keep the basic structure
    3. **Add Comments**: Include comments explaining complex logic or important changes
    4. **Handle Edge Cases**: Add proper error handling and edge case management
    5. **Be Thorough**: Ensure the fix addresses ALL issues mentioned in the error description
    6. **Test Rigorously**: Use the IFC model to validate your fixes before completion
    7. **Verify IfcOpenShell API Usage**: When fixing issues related to ifcopenshell functions, properties, or methods, ALWAYS use the query_ifcopenshell_docs tool first to verify correct usage before implementing fixes

    IMPLEMENTATION REQUIREMENTS:

    - **Correct Logic**: The function must work correctly for the described use case
    - **Proper Filtering**: If it filters data (e.g., by floor), it must actually filter correctly
    - **Type Hints**: Include proper type hints for parameters and return values
    - **Error Handling**: Follow CODE QUALITY CHECKLIST (see below)
    - **Documentation**: Clear docstring explaining what the function does
    - **No Side Effects**: Don't modify the IFC file or have unintended consequences

    CODE QUALITY CHECKLIST:

    1. **Exception Handling**:
       ✅ Catch specific exceptions (AttributeError, KeyError, RuntimeError)
       ✅ Use try-except ONLY in narrow scopes (not wrapping entire functions)
       ❌ NEVER use `except Exception: pass` without re-raising or logging

       Example - tracking skipped elements:
       ```python
       skipped = 0
       for elem in elements:
           try:
               process(elem)
           except AttributeError:  # Specific exception
               skipped += 1
               continue
       if skipped > 0:
           print(f"Warning: Skipped {skipped} elements")
       ```

    2. **None/Empty Validation**:
       ✅ Validate inputs at function start: `if not elements: return []`
       ✅ Check for None in grouping keys: `if key is None: key = "Undefined"`
       ✅ Use getattr with defaults: `val = getattr(elem, 'attr', 'default')`
       ❌ Don't create meaningless groups (e.g., grouping by None)

    3. **Result Validation**:
       ✅ Check results make sense before returning
       ✅ Document in docstring when function returns empty/partial results
       ✅ Report data loss (e.g., "Processed 45/50 elements, 5 skipped")

    4. **Defensive Attribute Access**:
       ✅ Required attributes: Check first with hasattr() or let it fail fast
       ✅ Optional attributes: Use getattr(elem, 'attr', default)
       ❌ Don't assume all elements have all attributes

    5. **Edge Cases to Handle**:
       - Empty input collections → return appropriate empty result
       - Elements missing expected attributes → skip with counter OR fail fast
       - None/null values in data → use "Undefined" or "Unknown" labels
       - Mixed types in collections → handle or document limitations

    ITERATION PROCESS:

    Use CodeAction to:
    - Write and test fixed implementations
    - Debug issues with the current approach
    - Validate against test cases from the error description
    - Refine the implementation based on testing results

    Use UpdatedHelperFunction only when:
    - You have thoroughly tested the implementation
    - All test cases from the error description pass
    - The function handles edge cases correctly
    - You are confident the fix is robust and complete

    CHANGES SUMMARY FORMAT:

    Briefly summarize the main changes made:
    - What was broken
    - How it was fixed
    - Key improvements made
    - Test results that validate the fix

    {{ ctx.output_format }}
  "#
}

// Test case 1: Faulty door counting function
test ToolFixerTest {
  functions [HelperFunctionDebugger]
  args {
    faulty_function_name "count_doors_by_floor"
    faulty_function_implementation #"""
def count_doors_by_floor(ifc_file_path: str, floor_name: str) -> int:
    """
    Count the number of doors on a specific building floor.

    Args:
        ifc_file_path: Path to the IFC file
        floor_name: Name of the floor/storey (e.g., 'Level 1', 'Ground Floor')

    Returns:
        Number of doors on the specified floor
    """
    ifc_file = ifcopenshell.open(ifc_file_path)
    doors = ifc_file.by_type('IfcDoor')

    # BUG: Returns ALL doors instead of filtering by floor_name
    return len(doors)
    """#
    error_description "The function ignores the floor_name parameter and returns ALL doors in the building (14) instead of just the doors on the specified floor (6 for Level 1). The function should filter doors by their ContainedInStructure relationships and only count doors where RelatingStructure.Name == floor_name."
    history_faulty_tool_use "Cobbie called count_doors_by_floor(ifc_file_path, 'Level 1') expecting to get only doors on Level 1, but got 14 (total doors) instead of 6 (Level 1 doors). The function was used to answer 'How many doors are on the ground floor?'"
    ifc_model_path "/Users/sylvainhellin/GitHub/4_phd/cobbie/src/db/bim_models/duplex/arc.ifc"
    other_bim_models_for_testing ["/Users/sylvainhellin/GitHub/4_phd/cobbie/src/db/bim_models/duplex/arc.ifc", "/Users/sylvainhellin/GitHub/4_phd/cobbie/src/db/bim_models/house.ifc"]
  }
}

// Test case 2: Function with logic error in property extraction
test ToolFixerTest_PropertyExtraction {
  functions [HelperFunctionDebugger]
  args {
    faulty_function_name "get_element_thickness"
    faulty_function_implementation #"""
def get_element_thickness(ifc_file_path: str, element_guid: str) -> float:
    """
    Get the thickness of an IFC element.

    Args:
        ifc_file_path: Path to the IFC file
        element_guid: GlobalId of the element

    Returns:
        Thickness value in meters
    """
    ifc_file = ifcopenshell.open(ifc_file_path)
    element = ifc_file.by_guid(element_guid)

    # BUG: Looking for wrong property name
    for pset in element.IsDefinedBy:
        if hasattr(pset, 'RelatingPropertyDefinition'):
            props = pset.RelatingPropertyDefinition.HasProperties
            for prop in props:
                if prop.Name == 'Width':  # Should be 'Thickness'
                    return prop.NominalValue.wrappedValue

    return 0.0
    """#
    error_description "The function looks for 'Width' property when it should look for 'Thickness' property. When called on a wall element that has Thickness=0.2m, the function returns 0.0 because it's searching for the wrong property name."
    ifc_model_path "/Users/sylvainhellin/GitHub/4_phd/cobbie/src/db/bim_models/duplex/arc.ifc"
  }
}

// Test case 3: Function with parameter validation issue
test ToolFixerTest_ParameterValidation {
  functions [HelperFunctionDebugger]
  args {
    faulty_function_name "calculate_area_by_type"
    faulty_function_implementation #"""
def calculate_area_by_type(ifc_file_path: str, ifc_type: str) -> float:
    """
    Calculate total area of elements of a specific type.

    Args:
        ifc_file_path: Path to the IFC file
        ifc_type: IFC element type (e.g., 'IfcWall', 'IfcSlab')

    Returns:
        Total area in square meters
    """
    ifc_file = ifcopenshell.open(ifc_file_path)
    elements = ifc_file.by_type(ifc_type)

    total_area = 0.0
    for element in elements:
        # BUG: Assumes all elements have geometry without checking
        geometry = ifcopenshell.geom.create_geometry_settings()
        shape = ifcopenshell.geom.create_shape(geometry, element)
        if shape and shape.geometry:
            area = shape.geometry.get_area()
            total_area += area

    return total_area
    """#
    error_description "The function fails when elements don't have geometry or when the IFC type doesn't exist. It should handle cases where geometry is not available and validate that the ifc_type parameter is valid before processing."
    ifc_model_path "/Users/sylvainhellin/GitHub/4_phd/cobbie/src/db/bim_models/duplex/arc.ifc"
  }
}
