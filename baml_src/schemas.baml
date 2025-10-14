// BAML schemas for BIM QA system
// Union types for CodeAct implementation

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