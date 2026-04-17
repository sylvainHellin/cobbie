// BAML schemas for the ACC pipeline

// Code execution action (loop mode)
class CodeAction {
  thoughts string @description("Reasoning for next step")
  python_code string @description("Code to execute")
}

// Helper function implementation result - final output from HelperFunctionCreator
class NewHelperFunction {
  thoughts string @description("Summary of development process, testing performed, and validation results")
  function_implementation string @description("Complete Python function implementation including imports, docstring, and type hints")
  success bool @description("Whether the function is complete, tested, and ready for use")
}

// ACC tool generalizability assessment - analyzes why a tool fails on validation data
class ACCToolAssessment {
  thoughts string @description("Step-by-step analysis of tool execution and validation results")

  diagnosis "overfitting" | "missing_generalization" | "implementation_bug" | "model_difference" | "unknown" @description(#"
    Root cause diagnosis:
    - overfitting: Tool relies on training-specific patterns (e.g., hardcoded values, specific element names)
    - missing_generalization: Tool misses valid cases due to incomplete logic (e.g., missing element types)
    - implementation_bug: Logic error in the tool implementation
    - model_difference: Validation model has structural differences that require different handling
    - unknown: Unable to determine cause from available information
  "#)

  improvement_hint string @description(#"
    Generic guidance for improving the tool. MUST NOT contain validation-specific GUIDs or element identifiers.
    Examples: "Consider checking all IfcSpace subtypes", "Handle spaces with multiple boundary conditions",
    "Check for classification variations in the Name property"
  "#)

  recommendation "keep_tool" | "retry_with_hint" @description(#"
    Final recommendation:
    - keep_tool: Tool is good enough despite imperfect validation (F1 >= threshold or best effort reached)
    - retry_with_hint: Try creating an improved version using the improvement_hint
  "#)

  confidence "high" | "medium" | "low" @description(#"
    Confidence in this diagnosis:
    - high: Clear pattern identified with strong evidence
    - medium: Likely cause identified but some uncertainty
    - low: Diagnosis is speculative due to limited information
  "#)
}
