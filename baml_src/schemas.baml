// BAML schemas for BIM QA system

// Code execution action (loop mode)
class CodeAction {
  thoughts string @description("Reasoning for next step")
  python_code string @description("Code to execute")
}

// Final answer action (completion mode)
class FinalAnswer {
  thoughts string @description("Summary of findings")
  answer string @description("Final answer to user's question")
}

// Tool creation result
class ToolCreationResult {
  function_name string
  function_implementation string
  success bool
}

// Answer verification result
class SimilarityResult {
similarity_score float
  correct_answer bool
  reasoning string
}

// Error analysis result
class ErrorAnalysisResult {
  error_category string @description("faulty_tool, missing_tool, other")
  function_name string?
  needs_new_tool bool
}

// Tool optimization result
class ToolOptimizationResult {
  improvement string @description("create_new_tool, merge_existing_tools, update_existing_tool, no_action_needed")
  function_name string?
  function_requirements string?
  existing_tool_names string[]?
}

// Answer evaluation result
class AnswerEvaluationResult {
  classification "correct" | "wrong" | "abstained" @description(#"
    Classification of the system response
  "#)

  justification string @description(#"
    Brief explanation (2-3 sentences) of why this classification was chosen.
  "#)

  confidence "high" | "medium" | "low" @description(#"
    Evaluator confidence level
  "#)
}

// Assessment result from ToolAssessor - tests function behavior without seeing implementation
class AssessmentResult {
  assessment_status "ok" | "needs_improvement" @description("'ok' if function works as expected, 'needs_improvement' if issues found")
  assessment_details string @description("Detailed explanation of test results and any issues discovered")
  test_execution_log string? @description("Log of function execution and test cases attempted")
}

// Extended result class for when tool creation is complete
class FunctionImplementation {
  function_implementation string
  confidence float?
  needs_improvement bool
}

// Improved implementation from ToolCorrector - addresses assessment feedback
class ImprovedImplementation {
  function_implementation string @description("Updated Python source code addressing assessment issues")
  reasoning string @description("Explanation of changes made and how they address the feedback")
  changes_summary string? @description("Brief summary of the main changes made")
}

// Cleaned code from CodeCleaner - fixes syntax and compilation errors
class CleanedCode {
  function_implementation string @description("Python code with syntax errors fixed")
  reasoning string @description("Explanation of syntax fixes and corrections applied")
  success bool @description("Whether the cleaning was successful")
}

// Aligned question-answer pair for dataset cleaning
class AlignedQAPair {
  thought string @description("Analysis of the alignment between question and answer, and reasoning for any changes")
  aligned_question string @description("Question reformulated to align with answer structure and scope (or original if already aligned)")
  aligned_answer string @description("Answer with improved formatting/clarity while preserving factual content (or original if already good)")
  was_modified bool @description("Whether any modifications were made to question or answer")
}

// Successful outcome - function has been tested and improved successfully
class TestAndImproveSuccess {
  function_implementation string @description("Final validated function implementation")
  assessment_details string @description("Final assessment confirming function works correctly")
  iterations_used int @description("Number of iterations needed to achieve success")
  total_time_seconds float @description("Total time taken for testing and improvement")
}

// Error outcome - testing and improvement process failed
class TestAndImproveError {
  error_message string @description("Detailed error description")
  iterations_completed int @description("Number of iterations completed before failure")
  final_assessment_status string? @description("Last known assessment status, if any")
  partial_function_implementation string? @description("Best function implementation achieved, if any")
}

// Category validation result for question-answer pairs
class CategoryValidationResult {
  validated_category string @description("The correct category (1, 2, 3, or 4) according to the taxonomy")
  updated bool @description("Whether the category was changed from the original")
  thought string @description("Reasoning for the category classification and any changes made")
}

// Helper function identification result from successful Cobbie executions
class NewToolAnalysis {
  thoughts string @description("Step-by-step analysis of the execution history to identify reusable patterns")
  new_tool bool @description("Whether a new helper function should be created (true) or not (false)")
  new_tool_name string @description("Suggested name for the new helper function (empty string if new_tool is false)")
  new_tool_description string @description("Detailed description of what the helper function should do, its parameters, return type, and use cases (empty string if new_tool is false)")
}

// Helper function implementation result - final output from HelperFunctionCreator
class NewHelperFunction {
  thoughts string @description("Summary of development process, testing performed, and validation results")
  function_implementation string @description("Complete Python function implementation including imports, docstring, and type hints")
  success bool @description("Whether the function is complete, tested, and ready for use")
}

// Faulty tool identification result - analyzes wrong answers to identify tool-related failures
class FaultyToolAnalysis {
  thoughts string @description("Chain-of-thought analysis of the execution history to identify tool-related failures")
  faulty_tool bool @description("Whether a faulty tool was identified as the primary cause of the wrong answer")
  faulty_tool_name string @description("Name of the faulty tool (empty string if faulty_tool is false)")
  error_description string @description("Summary of the error and test cases demonstrating the failure (empty string if faulty_tool is false)")
  confidence "high" | "medium" | "low" @description("Confidence level in this faulty tool identification")
}

// Tool fixing result - analyzes and fixes faulty helper functions
class UpdatedHelperFunction {
  thoughts string @description("Analysis of the faulty function and explanation of the fixing process")
  fixed_implementation string @description("Fixed Python function implementation that addresses the identified issues")
  changes_summary string @description("Summary of the main changes made to fix the function")
  success bool @description("Whether the function was successfully fixed and is ready for use")
  test_cases_provided string @description("Test cases that can be used to verify the fix works correctly")
}
