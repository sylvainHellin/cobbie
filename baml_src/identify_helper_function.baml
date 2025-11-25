// HelperFunctionIdentifier - Analyzes successful Cobbie executions to identify reusable helper functions
// This agent extracts generalizable patterns from successful question-answering sessions
// to build a library of high-level BIM/IFC analysis tools

function HelperFunctionIdentifier(
  history: string @description("Complete execution history from Cobbie: thoughts, code, results, and final answer"),
  example_question: string @description("The question that was successfully answered by Cobbie"),
  existing_helper_functions: string @description("List of all existing helper functions with their docstrings and signatures")
) -> NewToolAnalysis {
  client GLM_4_6
  prompt #"
    You are an expert Python developer and software architect specializing in BIM (Building Information Modeling) systems.

    Your task is to analyze a successful execution from COBBIE (a code-based BIM question-answering agent) and determine if a reusable helper function should be extracted.

    EXECUTION CONTEXT:

    Question Answered:
    {{ example_question }}

    Execution History (thoughts, code, and results):
    {{ history }}

    Existing Helper Functions:
    {{ existing_helper_functions }}

    ENHANCEMENT VS CREATION DECISION:

    Before recommending a new tool, check if an existing tool could be ENHANCED instead.

    **Consider ENHANCEMENT (action="enhance_existing") if:**
    1. Existing tool provides 70%+ of needed functionality
    2. Missing functionality can be added via optional parameters with sensible defaults
    3. Enhancement maintains backward compatibility (existing code works unchanged)
    4. Combined tool remains focused and understandable

    **Choose CREATION (action="create_new") if:**
    1. No existing tool provides 70%+ overlap
    2. Pattern is fundamentally different from existing tools
    3. Enhancement would make existing tool too complex
    4. New functionality is orthogonal to existing tools

    **Choose NONE (action="none") if:**
    1. Existing tools already handle this adequately
    2. Pattern is too specific to this question
    3. Direct ifcopenshell calls are clearer

    YOUR ANALYSIS CRITERIA:

    A helper function SHOULD be created OR enhanced if:
    1. **Generalizability**: Pattern applies to similar questions
    2. **Abstraction Level**: Higher-level than direct ifcopenshell calls
    3. **Reusability**: Multiple future questions could benefit
    4. **Enhancement Opportunity**: Existing tool is close but missing one feature
    5. **Clear Interface**: Clear parameters with sensible defaults
    6. **Complexity Reduction**: It simplifies common BIM analysis tasks

    A helper function SHOULD NOT be created if:
    1. **Overfitting**: The code is too specific to this exact question or model
    2. **Trivial**: It's just a simple wrapper around one ifcopenshell call
    3. **Redundant**: An existing helper function already does this (or can easily be extended)
    4. **Hard-coded values**: The code contains model-specific constants or assumptions
    5. **One-off**: It's unlikely to be useful for other questions
    6. **Too complex**: It combines unrelated operations that shouldn't be bundled together

    ANALYSIS PROCESS:

    1. Examine the execution history to identify:
       - What ifcopenshell operations were used
       - What patterns or logic were applied
       - What intermediate results were computed
       - What made this approach successful

    2. Consider generalization:
       - Can this pattern be abstracted to work with different IFC element types?
       - Can it be parameterized to handle various filtering/sorting criteria?
       - Does it represent a common BIM analysis operation?

    3. Check against existing functions:
       - Is there overlap with existing helper functions?
       - Could an existing function be extended instead?

    4. Define the helper function concept (if one should be created):
       - Function name: Clear, descriptive, follows Python naming conventions
       - Parameters: Generic, typed, well-defined
       - Return type: Clear structure (list, dict, int, str, etc.)
       - Purpose: Concise description of what it does and when to use it

    IMPORTANT GUIDELINES:

    - Prefer creating functions that encapsulate common BIM domain operations (e.g., "get_elements_by_property", "calculate_total_area")
    - Avoid creating functions that are just thin wrappers (e.g., "get_all_walls" if it just calls model.by_type('IfcWall'))
    - Focus on patterns that appeared necessary because ifcopenshell documentation queries were made
    - Think about what would help COBBIE solve similar questions faster in the future

    OUTPUT REQUIREMENTS:

    1. Set `action` to "create_new", "enhance_existing", or "none"
    2. For "enhance_existing":
       - `tool_name` = existing tool to enhance
       - `tool_description` = what parameters to add and how they extend functionality
       - `existing_tool_for_enhancement` = same as tool_name
    3. For "create_new":
       - `tool_name` = new function name
       - `tool_description` = full specification including parameters, return type, and use cases
       - `existing_tool_for_enhancement` = null
    4. For "none":
       - `tool_name` = empty string
       - `tool_description` = empty string
       - `existing_tool_for_enhancement` = null

    {{ ctx.output_format }}
  "#
}

// Test case for helper function identification with a clear reusable pattern
test HelperFunctionIdentifierPositiveTest {
  functions [HelperFunctionIdentifier]
  args {
    example_question "How many doors are on the ground floor?"
    history #"
      --- Iteration 1 ---
      Thoughts: I need to first understand how to filter elements by floor/storey in IFC. Let me search the documentation.

      Code:
      result = query_ifcopenshell_docs("filter elements by storey level")

      Result:
      IfcRelContainedInSpatialStructure relates elements to spatial structures like storeys...

      --- Iteration 2 ---
      Thoughts: Now I'll get all doors and filter by the ground floor storey

      Code:
      import ifcopenshell
      model = ifcopenshell.open(path_ifc_model)

      # Get ground floor storey
      ground_floor = None
      for storey in model.by_type('IfcBuildingStorey'):
          if 'ground' in storey.Name.lower() or storey.Name == '0':
              ground_floor = storey
              break

      # Get doors in ground floor
      doors_on_ground = []
      for rel in ground_floor.ContainsElements:
          for element in rel.RelatedElements:
              if element.is_a('IfcDoor'):
                  doors_on_ground.append(element)

      print(f"Found {len(doors_on_ground)} doors on ground floor")

      Result:
      Found 6 doors on ground floor

      --- Final ---
      Thoughts: Successfully identified all doors on the ground floor by traversing the spatial structure relationships.
      Answer: There are 6 doors on the ground floor.
    "#
    existing_helper_functions #"
      def query_ifcopenshell_docs(query: str) -> str:
          '''Search ifcopenshell documentation for information'''

      def web_search(query: str) -> str:
          '''Search the web for general information'''
    "#
  }
}

// Test case for a pattern that should NOT result in a helper function (too specific)
test HelperFunctionIdentifierNegativeTest {
  functions [HelperFunctionIdentifier]
  args {
    example_question "What is the height of wall with GlobalId '2O2Fr$t4X7Zf8NOew3FL9r'?"
    history #"
      --- Iteration 1 ---
      Thoughts: I need to find the specific wall by GlobalId and get its height

      Code:
      import ifcopenshell
      model = ifcopenshell.open(path_ifc_model)

      wall = model.by_guid('2O2Fr$t4X7Zf8NOew3FL9r')
      height = wall.Height

      print(f"Wall height: {height}")

      Result:
      Wall height: 3.5

      --- Final ---
      Thoughts: Found the wall and extracted its height property directly.
      Answer: The wall has a height of 3.5 meters.
    "#
    existing_helper_functions #"
      def query_ifcopenshell_docs(query: str) -> str:
          '''Search ifcopenshell documentation for information'''

      def web_search(query: str) -> str:
          '''Search the web for general information'''
    "#
  }
}

// Test case with existing similar function (should not create duplicate)
test HelperFunctionIdentifierRedundantTest {
  functions [HelperFunctionIdentifier]
  args {
    example_question "How many windows are in the building?"
    history #"
      --- Iteration 1 ---
      Thoughts: I'll count all windows in the model

      Code:
      import ifcopenshell
      model = ifcopenshell.open(path_ifc_model)
      windows = model.by_type('IfcWindow')
      print(f"Total windows: {len(windows)}")

      Result:
      Total windows: 42

      --- Final ---
      Thoughts: Counted all window elements in the model.
      Answer: There are 42 windows in the building.
    "#
    existing_helper_functions #"
      def query_ifcopenshell_docs(query: str) -> str:
          '''Search ifcopenshell documentation for information'''

      def web_search(query: str) -> str:
          '''Search the web for general information'''

      def count_elements_by_type(ifc_file_path: str, ifc_type: str) -> int:
          '''Count the number of elements of a specific IFC type in a model

          Args:
              ifc_file_path: Path to the IFC file
              ifc_type: IFC element type (e.g., 'IfcWall', 'IfcWindow')

          Returns:
              int: Count of elements of the specified type
          '''
    "#
  }
}
