// HelperFunctionAssessor - Analyzes execution history to determine if a specific helper function was useful
// This agent examines how a newly created or debugged tool was used (or not used) during Cobbie's execution
// to provide targeted feedback for deciding whether to keep, discard, or improve the tool

function HelperFunctionAssessor(
  execution_history: string @description("Complete execution history from Cobbie: thoughts, code, results, and final answer"),
  original_question: string @description("The original question (without enhancement) that was being answered"),
  ground_truth_answer: string @description("The correct/expected answer to the question"),
  tested_tool_name: string @description("Name of the helper function being assessed"),
  tested_tool_description: string @description("Description of what the helper function is supposed to do"),
  final_answer: string @description("The final answer provided by Cobbie after using (or not using) the tool"),
  answer_correctness: "correct" | "wrong" | "abstained" @description("Classification of the final answer from answer verifier")
) -> HelperFunctionAssessment {
  client GLM_4_6
  prompt #"
    You are an expert Python developer and software architect specializing in BIM (Building Information Modeling) systems.

    Your task is to analyze a Cobbie execution to determine if a specific helper function was useful and should be kept in the tool library.

    CONTEXT:

    We recently created or debugged a helper function and want to assess its value by examining how Cobbie used it (or didn't use it) when answering a question.

    TESTED HELPER FUNCTION:
    Name: {{ tested_tool_name }}
    Description: {{ tested_tool_description }}

    QUESTION & ANSWER:
    Original Question: {{ original_question }}
    Ground Truth (Correct Answer): {{ ground_truth_answer }}
    Cobbie's Final Answer: {{ final_answer }}
    Answer Correctness: {{ answer_correctness }}

    EXECUTION HISTORY:
    {{ execution_history }}

    YOUR ANALYSIS TASK:

    Examine the execution history and determine:

    1. **Was the tool used?**
       - Check if {{ tested_tool_name }} appears in any code blocks
       - Look for function calls to {{ tested_tool_name }}
       - Note if the tool was mentioned in thoughts but not actually called

    2. **How was the tool used?** (if at all)
       - What parameters were passed?
       - Were the parameters correct and appropriate?
       - What did the tool return?
       - How did Cobbie use the tool's output?

    3. **Did the tool contribute to the answer?**
       - Compare tool outputs with the ground truth answer
       - Trace how tool results flowed through subsequent code
       - Determine if the tool helped reach the correct answer

    4. **What is the tool's quality assessment?**
       - helpful: Tool was used correctly and contributed to correctness
       - not_used: Tool was available but never called
       - ignored: Tool was mentioned/considered but explicitly not used
       - misused: Tool was called incorrectly (wrong params, wrong context)
       - harmful: Tool was used and led to incorrect results

    CRITICAL EVALUATION CRITERIA:

    **Tool is HELPFUL if:**
    - Correctly used and contributed to correct answer
    - Provided essential functionality not easily achieved otherwise
    - Enabled more efficient or elegant solution
    - Would be valuable for similar future questions

    **Tool should be DISCARDED if:**
    - Not used when it could have been helpful
    - Used incorrectly or caused errors
    - Provided no meaningful contribution
    - Replaced by simpler approaches
    - Is redundant with existing tools

    **Tool needs IMPROVEMENT if:**
    - Used but with difficulty or errors
    - Potential utility but poor implementation
    - Wrong interface or return format
    - Could be more efficient or robust

    **UNCLEAR assessment when:**
    - Limited usage or insufficient test coverage
    - Mixed indicators of utility
    - Edge case or question-specific scenario
    - Tool wasn't needed for this specific question but might be useful for others

    DETAILED REQUIREMENTS:

    1. **Trace Tool Usage**: Identify every call to {{ tested_tool_name }} with context
    2. **Validate Usage**: Check if parameters were correct and results reasonable
    3. **Assess Contribution**: Evaluate how the tool's output influenced the final answer
    4. **Consider Alternatives**: Compare with how Cobbie solved it without the tool (if applicable)
    5. **Project Future Value**: Consider utility for other similar questions

    IMPORTANT GUIDELINES:

    - **Focus on this specific tool only** - Ignore other tools' performance
    - **Be evidence-based** - Base your assessment on what actually happened in the execution
    - **Consider the context** - A tool not being used might be okay if it wasn't needed
    - **Trace causality** - If the answer is wrong, determine if this tool caused it
    - **Distinguish misuse from bugs** - Cobbie using it wrong vs tool having a bug

    RECOMMENDATION LOGIC:

    - **keep_tool** if:
      - Tool was used correctly and helped produce correct answer
      - Tool was not used this time but seems generally useful (not applicable to this specific question)

    - **discard_tool** if:
      - Tool was used and produced harmful results
      - Tool was not used because a better approach exists
      - Tool is redundant with existing tools
      - Tool is too specific and unlikely to be useful elsewhere

    - **improve_tool** if:
      - Tool was misused but seems to have potential with better interface/docs
      - Tool was used but produced incorrect results (bug in implementation)
      - Tool concept is good but needs refinement

    - **unclear** if:
      - Tool wasn't used and it's ambiguous whether it should have been
      - Mixed signals (some helpful aspects, some harmful)
      - Need more test cases to determine value

    CONFIDENCE ASSIGNMENT:

    - **high**: Clear, unambiguous evidence supports the assessment
    - **medium**: Strong indicators but some uncertainty or edge cases
    - **low**: Limited evidence, conflicting signals, or highly context-dependent

    {{ ctx.output_format }}
  "#
}

// Test case 1: Tool was helpful and used correctly
test HelperFunctionAssessorHelpfulTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "How many doors are on the ground floor?"
    ground_truth_answer "There are 6 doors on the ground floor."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "There are 6 doors on the ground floor."
    answer_correctness "correct"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I should use the new get_elements_by_building_storey function to find doors by floor.

      Code:
      doors_by_floor = get_elements_by_building_storey(path_ifc_model, 'IfcDoor')
      print(f"Doors by floor: {list(doors_by_floor.keys())}")

      Result:
      Doors by floor: ['Ground Floor', 'First Floor', 'Second Floor']

      --- Iteration 2 ---
      Thoughts: Now I can count the doors on the ground floor.

      Code:
      ground_floor_doors = doors_by_floor.get('Ground Floor', [])
      print(f"Ground floor doors: {len(ground_floor_doors)}")

      Result:
      Ground floor doors: 6

      --- Final Answer ---
      Thoughts: Successfully used the get_elements_by_building_storey function to find and count doors on the ground floor.
      Answer: There are 6 doors on the ground floor.
    "#
  }
}

// Test case 2: Tool was not used but alternative approach worked
test HelperFunctionAssessorNotUsedTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "What is the total floor area of the building?"
    ground_truth_answer "The total floor area is 450 square meters."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "The total floor area is 450 square meters."
    answer_correctness "correct"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I need to calculate total floor area. I'll get all IfcSlab elements and sum their areas.

      Code:
      import ifcopenshell
      import ifcopenshell.util.element as util
      model = ifcopenshell.open(path_ifc_model)
      slabs = model.by_type('IfcSlab')
      total_area = sum(util.get_psets(slab).get('Qto_SlabBaseQuantities', {}).get('GrossArea', 0) for slab in slabs)
      print(f"Total floor area: {total_area}")

      Result:
      Total floor area: 450

      --- Final Answer ---
      Thoughts: Calculated total floor area by summing slab areas.
      Answer: The total floor area is 450 square meters.
    "#
  }
}

// Test case 3: Tool was misused (wrong parameters)
test HelperFunctionAssessorMisusedTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "How many windows are on the first floor?"
    ground_truth_answer "There are 8 windows on the first floor."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "There are 0 windows on the first floor."
    answer_correctness "wrong"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I'll use the new function to get windows by floor. I think I should pass the floor name as a parameter.

      Code:
      first_floor_windows = get_elements_by_building_storey(path_ifc_model, 'First Floor')
      print(f"Windows: {first_floor_windows}")

      Result:
      Error: get_elements_by_building_storey() takes 2 positional arguments but 2 were given. Expected (ifc_file_path, element_type), got (ifc_file_path, 'First Floor')

      --- Iteration 2 ---
      Thoughts: I got an error. Let me try a different approach.

      Code:
      import ifcopenshell
      model = ifcopenshell.open(path_ifc_model)
      windows = model.by_type('IfcWindow')
      # I don't know how to filter by floor now
      print(f"Total windows: {len(windows)}")

      Result:
      Total windows: 24

      --- Final Answer ---
      Thoughts: I couldn't figure out how to filter by floor, giving up.
      Answer: There are 0 windows on the first floor.
    "#
  }
}

// Test case 4: Tool was harmful (returned wrong data)
test HelperFunctionAssessorHarmfulTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "How many doors are on the ground floor?"
    ground_truth_answer "There are 6 doors on the ground floor."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "There are 12 doors on the ground floor."
    answer_correctness "wrong"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I'll use get_elements_by_building_storey to find doors by floor.

      Code:
      doors_by_floor = get_elements_by_building_storey(path_ifc_model, 'IfcDoor')
      ground_floor_doors = doors_by_floor.get('Ground Floor', [])
      print(f"Ground floor doors: {len(ground_floor_doors)}")

      Result:
      Ground floor doors: 12

      --- Final Answer ---
      Thoughts: The function returned 12 doors on the ground floor.
      Answer: There are 12 doors on the ground floor.
    "#
  }
}
