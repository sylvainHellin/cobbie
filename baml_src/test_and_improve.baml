// BAML implementation for TestAndImprove module replacing DSPy version
// Maintains strict separation between ToolAssessor (tests without seeing implementation)
// and ToolCorrector (improves with feedback)

// Assessment result from ToolAssessor - tests function behavior without seeing implementation
class AssessmentResult {
  assessment_status string @description("'ok' if function works as expected, 'needs_improvement' if issues found")
  assessment_details string @description("Detailed explanation of test results and any issues discovered")
  test_execution_log string? @description("Log of function execution and test cases attempted")
  confidence float? @description("Confidence level in the assessment (0.0-1.0)")
}

// Improved implementation from ToolCorrector - addresses assessment feedback
class ImprovedImplementation {
  function_implementation string @description("Updated Python source code addressing assessment issues")
  improvement_reasoning string @description("Explanation of changes made and how they address the feedback")
  confidence float? @description("Confidence level in the improvements (0.0-1.0)")
  changes_summary string? @description("Brief summary of the main changes made")
}

// Cleaned code from CodeCleaner - fixes syntax and compilation errors
class CleanedCode {
  function_implementation string @description("Python code with syntax errors fixed")
  cleaning_reasoning string @description("Explanation of syntax fixes and corrections applied")
  success bool @description("Whether the cleaning was successful")
}

// ToolAssessor function - tests function behavior using CodeAct pattern
// Critical: This function uses CodeAct to execute code and test the function
// Returns either CodeAction (continue testing) or AssessmentResult (final assessment)
function ToolAssessor(
  function_name: string,
  function_requirements: string,
  path_ifc_model: string,
  available_tools: string,
  previous_attempts: string? @description("Previous test execution results, if any")
) -> CodeAction | AssessmentResult {
  client ZAICodingPlan
  prompt #"
    You are testing a Python function that has been created to meet specific requirements.
    Your role is to thoroughly test the function as a BLACK BOX - you can use the function but cannot see its implementation.

    FUNCTION TO TEST: {{ function_name }}

    REQUIREMENTS TO VERIFY:
    {{ function_requirements }}

    TEST MODEL PATH: {{ path_ifc_model }}

    AVAILABLE TOOLS:
    {{ available_tools }}

    {% if previous_attempts %}
    PREVIOUS TEST RESULTS:
    {{ previous_attempts }}
    {% endif %}

    CRITICAL INSTRUCTIONS:
    You must return EITHER a CodeAction object OR an AssessmentResult object - NOT explanations.

    If you need to run more test code, return CodeAction with:
    - python_code: The exact Python code to execute
    - thoughts: Brief explanation of what you're testing

    If you have enough information for final assessment, return AssessmentResult with:
    - assessment_status: "ok" or "needs_improvement"
    - assessment_details: Detailed explanation of test results
    - test_execution_log: Optional log of tests performed
    - confidence: Optional confidence level (0.0-1.0)

    TESTING APPROACH:
    1. Test normal operation with the provided IFC model
    2. Test edge cases (invalid paths, wrong file types, etc.)
    3. Verify return types and error handling
    4. Check robustness and performance

    {{ ctx.output_format }}
  "#
}

// ToolCorrector function - improves implementation based on detailed assessment feedback
// Uses CodeAct pattern to test improvements and iterate
// Returns either CodeAction (continue improving) or ImprovedImplementation (final result)
function ToolCorrector(
  function_requirements: string,
  function_name: string,
  current_function_implementation: string,
  detailed_assessment: string,
  path_ifc_model: string,
  available_tools: string,
  previous_attempts: string? @description("Previous improvement attempts, if any")
) -> CodeAction | ImprovedImplementation {
  client ZAICodingPlan
  prompt #"
    You are improving a Python function based on detailed assessment feedback.

    FUNCTION NAME: {{ function_name }}

    REQUIREMENTS:
    {{ function_requirements }}

    CURRENT IMPLEMENTATION:
    {{ current_function_implementation }}

    ASSESSMENT FEEDBACK TO ADDRESS:
    {{ detailed_assessment }}

    TEST MODEL PATH: {{ path_ifc_model }}

    AVAILABLE TOOLS:
    {{ available_tools }}

    {% if previous_attempts %}
    PREVIOUS IMPROVEMENT ATTEMPTS:
    {{ previous_attempts }}
    {% endif %}

    CRITICAL INSTRUCTIONS:
    You must return EITHER a CodeAction object OR an ImprovedImplementation object - NOT explanations.

    If you need to test code or continue improving, return CodeAction with:
    - python_code: The exact Python code to execute
    - thoughts: Brief explanation of what you're testing or improving

    If the function is fully improved and ready, return ImprovedImplementation with:
    - function_implementation: The complete improved Python code
    - improvement_reasoning: Explanation of changes made
    - confidence: Optional confidence level (0.0-1.0)
    - changes_summary: Optional brief summary of main changes

    IMPROVEMENT REQUIREMENTS:
    1. Fix every issue mentioned in the assessment feedback
    2. Ensure proper return types (int, str, list, dict as specified)
    3. Include comprehensive docstrings and type hints
    4. Add error handling with meaningful error messages
    5. Follow Python best practices for readability

    {{ ctx.output_format }}
  "#
}

// CodeCleaner function - fixes syntax errors and compilation issues
// Replaces DSPy ChainOfThought with direct BAML implementation
function CodeCleaner(
  faulty_code: string,
  error_message: string
) -> CleanedCode {
  client ZAICodingPlan
  prompt #"
    Fix syntax and compilation errors in Python function source code.

    FAULTY CODE:
    {{ faulty_code }}

    ERROR MESSAGE:
    {{ error_message }}

    Your task is to fix the syntax errors and return a CleanedCode object with:
    - function_implementation: The corrected Python code
    - cleaning_reasoning: Brief explanation of fixes made
    - success: boolean indicating if cleaning was successful

    Fix only syntax errors, import issues, and compilation problems.
    Do not change the fundamental logic or add new functionality.
    Ensure the code can execute without syntax errors.

    {{ ctx.output_format }}
  "#
}

// Test functions for validation

test ToolAssessorTest {
  functions [ToolAssessor]
  args {
    function_name "count_doors"
    function_requirements "Count all doors in an IFC model. Return an integer count."
    path_ifc_model "/Users/sylvainhellin/GitHub/4_phd/bim-qas/src/experiment/bim_models/duplex/arc.ifc"
    available_tools #"
      def count_doors(ifc_file_path: str) -> int:
          '''Count all doors in an IFC model'''

      def web_search(query: str) -> str:
          '''Search the web for information'''
    "#
  }
}

test ToolCorrectorTest {
  functions [ToolCorrector]
  args {
    function_name "count_doors"
    function_requirements "Count all doors in an IFC model. Return an integer count."
    current_function_implementation #"
      def count_doors(ifc_file_path: str) -> int:
          """Count all doors in an IFC model."""
          model = ifcopenshell.open(ifc_file_path)
          doors = model.by_type("IfcDoor")
          return str(len(doors))  # Wrong return type
    "#
    detailed_assessment "The function correctly counts doors (14) but returns a string instead of an integer, violating requirement #4. The function signature indicates it should return an integer."
    path_ifc_model "/Users/sylvainhellin/GitHub/4_phd/bim-qas/src/experiment/bim_models/duplex/arc.ifc"
    available_tools #"
      def web_search(query: str) -> str:
          '''Search the web for information'''
    "#
  }
}

test CodeCleanerTest {
  functions [CodeCleaner]
  args {
    faulty_code #"
      def count_doors(ifc_file_path: str) -> int:
          """Count all doors in an IFC model."""
          model = ifcopenshell.open(ifc_file_path)  # Missing import
          doors = model.by_type("IfcDoor"  # Missing closing parenthesis
          return str(len(doors))
    "#
    error_message "'(' was never closed (<string>, line 4)"
  }
}