// FaultyToolIdentifier - Analyzes wrong answers from Cobbie to identify faulty tools
// This agent examines failed question-answering sessions where the answer was classified as "wrong"
// to determine if the failure was caused by a faulty helper function

function FaultyToolIdentifier(
  history: string @description("Complete execution history from Cobbie: thoughts, code, results, and final answer"),
  question: string @description("The question that Cobbie attempted to answer"),
  ground_truth: string @description("The correct/expected answer to the question"),
  provided_answer: string @description("The incorrect answer that Cobbie provided"),
  justification: string @description("Justification from the answer verifier explaining why the answer was classified as wrong"),
  existing_helper_functions: string @description("List of all existing helper functions with their docstrings and signatures")
) -> FaultyToolAnalysis {
  client GLM_4_6
  prompt #"
    You are an expert Python developer and software architect specializing in BIM (Building Information Modeling) systems.

    Your task is to analyze a FAILED execution from COBBIE (a code-based BIM question-answering agent) to determine if the wrong answer was caused by a faulty helper function (tool).

    EXECUTION CONTEXT:

    Question Asked:
    {{ question }}

    Ground Truth (Correct Answer):
    {{ ground_truth }}

    Provided Answer (Wrong):
    {{ provided_answer }}

    Answer Verifier's Justification:
    {{ justification }}

    Execution History (thoughts, code, and results):
    {{ history }}

    Available Helper Functions:
    {{ existing_helper_functions }}

    YOUR ANALYSIS TASK:

    Determine if the wrong answer was caused by a **faulty tool** (a helper function that returned incorrect results or behaved unexpectedly).

    ANALYSIS CRITERIA:

    A tool is FAULTY if:
    1. **Incorrect Return Value**: The function returned wrong data (e.g., counted wrong elements, extracted wrong properties)
    2. **Logic Error**: The function's implementation has a bug that causes incorrect behavior
    3. **Edge Case Failure**: The function fails on specific inputs or model structures
    4. **Parameter Handling Issue**: The function mishandles parameters or has incorrect assumptions
    5. **Data Extraction Error**: The function extracts data from the IFC model incorrectly

    A tool is NOT FAULTY if:
    1. **Missing Tool**: No suitable tool exists (the system needs a NEW tool, not a fix to an existing one)
    2. **Correct Tool, Wrong Usage**: Cobbie called the tool incorrectly (wrong parameters, wrong context)
    3. **Reasoning Error**: Cobbie's logic or approach was flawed, not the tool itself
    4. **Multiple Tool Issue**: Cobbie needed to use multiple tools but didn't
    5. **Context/Prompt Issue**: Cobbie misunderstood the question or requirements
    6. **Iteration Limit**: Cobbie ran out of iterations before completing the task

    IMPORTANT GUIDELINES:

    1. **Focus on Tool Behavior**: Examine what each tool RETURNED vs what it SHOULD have returned
    2. **Compare with Ground Truth**: Check if tool outputs align with what's needed for the correct answer
    3. **Trace Data Flow**: Follow how data from tools flowed through Cobbie's code
    4. **Worst Offender**: If multiple tools are faulty, identify the PRIMARY/WORST one
    5. **Be Conservative**: Only mark as faulty_tool if you have STRONG evidence the tool itself is broken
    6. **Test Cases**: If faulty, provide SPECIFIC test cases that would demonstrate the failure

    ANALYSIS PROCESS:

    1. Review the execution history:
       - What tools were called and with what parameters?
       - What did each tool return?
       - How did Cobbie use the tool outputs?

    2. Compare tool outputs with ground truth:
       - Given the ground truth answer, what should the tools have returned?
       - Do the tool outputs contradict what's needed for correctness?

    3. Identify the root cause:
       - Is the tool implementation wrong?
       - Or is this a usage issue, missing tool, or reasoning error?

    4. If faulty tool identified:
       - Name the specific tool
       - Describe what's wrong (summary)
       - Provide test cases that demonstrate the failure
       - Assign confidence level

    ERROR DESCRIPTION FORMAT (if faulty_tool is true):

    Summary: [Brief 2-3 sentence description of what's wrong with the tool]

    Test Cases:
    - Test Case 1: [Describe inputs and expected vs actual behavior]
    - Test Case 2: [Another test case demonstrating the failure]
    - Test Case 3: [Optional third test case]

    CONFIDENCE LEVELS:

    - **high**: Clear evidence the tool is faulty, multiple indicators point to tool error
    - **medium**: Strong suspicion the tool is faulty, but some ambiguity remains
    - **low**: Possible tool fault, but could also be other factors

    {{ ctx.output_format }}
  "#
}

// Test case 1: Faulty tool - function returns incorrect count
test FaultyToolPositiveTest {
  functions [FaultyToolIdentifier]
  args {
    question "How many doors have a fire rating of at least 30 minutes?"
    ground_truth "There are 3 doors with a fire rating of at least 30 minutes."
    provided_answer "There are 15 doors with a fire rating of at least 30 minutes."
    justification "The system response contains incorrect numerical information. The ground truth states 3 doors, but the system reported 15. This is a significant discrepancy and represents a factual error."
    history #"
      --- Iteration 1 ---
      Thoughts: I need to count the doors. Let me use the available tool to count doors by type.

      Code:
      result = count_doors_by_fire_rating(path_ifc_model, min_fire_rating=30)
      print(f"Emergency exit doors: {result}")

      Result:
      Emergency exit doors: 15

      --- Final Answer ---
      Thoughts: The count_doors_by_fire_rating function returned 15 doors with fire rating >= 30 minutes.
      Answer: There are 15 doors with a fire rating of at least 30 minutes.
    "#
    existing_helper_functions #"
      def query_ifcopenshell_docs(query: str) -> str:
          '''Search ifcopenshell documentation for information'''

      def web_search(query: str) -> str:
          '''Search the web for general information'''

      def count_doors_by_fire_rating(ifc_file_path: str, min_fire_rating: int) -> int:
          '''Count doors that meet minimum fire rating requirements

          Args:
              ifc_file_path: Path to the IFC file
              min_fire_rating: Minimum fire rating in minutes

          Returns:
              Number of doors with fire rating >= min_fire_rating
          '''
    "#
  }
}

// Test case 2: Not a faulty tool - missing tool scenario
test FaultyToolNegativeTest_MissingTool {
  functions [FaultyToolIdentifier]
  args {
    question "What is the total thermal resistance (R-value) of the exterior walls?"
    ground_truth "The total thermal resistance of the exterior walls is 4.5 m²K/W."
    provided_answer "I cannot determine the thermal resistance as the required property information is not directly available in the model."
    justification "The system abstained from providing a specific answer when ground truth shows a specific value should be calculable from the model data."
    history #"
      --- Iteration 1 ---
      Thoughts: I need to find thermal resistance properties of walls. Let me search for walls first.

      Code:
      import ifcopenshell
      model = ifcopenshell.open(path_ifc_model)
      walls = model.by_type('IfcWall')
      print(f"Found {len(walls)} walls")

      Result:
      Found 25 walls

      --- Iteration 2 ---
      Thoughts: I need to get thermal properties, but I don't have a tool for this. Let me try to find them manually.

      Code:
      for wall in walls[:3]:
          psets = ifcopenshell.util.element.get_psets(wall)
          print(f"Wall {wall.GlobalId}: {psets}")

      Result:
      Wall 2O2Fr$t4X7Zf8NOew3FL9r: {'Pset_WallCommon': {'ThermalTransmittance': 0.22}}
      Wall 3P3Gs%u5Y8Ag9OPfx4GM0s: {'Pset_WallCommon': {'ThermalTransmittance': 0.22}}
      Wall 4Q4Ht&v6Z9Bh0QPgy5HN1t: {'Pset_WallCommon': {'ThermalTransmittance': 0.22}}

      --- Final Answer ---
      Thoughts: I found thermal transmittance (U-value) but not R-value directly. I would need to calculate R = 1/U, but I'm not confident about handling all wall types correctly.
      Answer: I cannot determine the thermal resistance as the required property information is not directly available in the model.
    "#
    existing_helper_functions #"
      def query_ifcopenshell_docs(query: str) -> str:
          '''Search ifcopenshell documentation for information'''

      def web_search(query: str) -> str:
          '''Search the web for general information'''

      def get_element_properties(ifc_file_path: str, element_guid: str) -> dict:
          '''Get all properties of a specific IFC element

          Args:
              ifc_file_path: Path to the IFC file
              element_guid: GlobalId of the element

          Returns:
              Dictionary of property sets and their values
          '''
    "#
  }
}

// Test case 3: Not a faulty tool - reasoning error by Cobbie
test FaultyToolNegativeTest_ReasoningError {
  functions [FaultyToolIdentifier]
  args {
    question "How many windows are on the north-facing facade?"
    ground_truth "There are 8 windows on the north-facing facade."
    provided_answer "There are 24 windows on the north-facing facade."
    justification "The system response provides an incorrect count. The ground truth states 8 windows on the north facade, but the system reported 24, which appears to be counting all windows in the building rather than just north-facing ones."
    history #"
      --- Iteration 1 ---
      Thoughts: I need to count windows. Let me get all windows in the building.

      Code:
      windows = get_elements_by_type(path_ifc_model, 'IfcWindow')
      print(f"Total windows: {len(windows)}")

      Result:
      Total windows: 24

      --- Iteration 2 ---
      Thoughts: I have the window count. Now I should filter by orientation, but I'm not sure how to determine north-facing. Let me just provide the total count.

      Code:
      # The model has 24 windows total
      print("Windows found:", len(windows))

      Result:
      Windows found: 24

      --- Final Answer ---
      Thoughts: I counted all windows in the building.
      Answer: There are 24 windows on the north-facing facade.
    "#
    existing_helper_functions #"
      def query_ifcopenshell_docs(query: str) -> str:
          '''Search ifcopenshell documentation for information'''

      def web_search(query: str) -> str:
          '''Search the web for general information'''

      def get_elements_by_type(ifc_file_path: str, ifc_type: str) -> list:
          '''Get all elements of a specific IFC type

          Args:
              ifc_file_path: Path to the IFC file
              ifc_type: IFC element type (e.g., 'IfcWall', 'IfcWindow')

          Returns:
              List of IFC elements of the specified type
          '''

      def get_element_orientation(ifc_file_path: str, element_guid: str) -> str:
          '''Get the orientation/facing direction of an element

          Args:
              ifc_file_path: Path to the IFC file
              element_guid: GlobalId of the element

          Returns:
              Orientation as compass direction (e.g., 'North', 'South', 'East', 'West')
          '''
    "#
  }
}
