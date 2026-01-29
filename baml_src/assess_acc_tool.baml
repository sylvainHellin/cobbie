// ACCToolAssessor - Analyzes why an ACC compliance tool fails on validation data
// This agent examines tool execution and validation metrics to diagnose generalization issues
// IMPORTANT: This function receives validation METRICS only (counts, not specific GUIDs) to prevent information leakage

function ACCToolAssessor(
  // Rule context
  rule_title: string @description("Title of the compliance rule being checked (e.g., '304_3_1_circular_space')"),
  rule_code: string @description("Code reference for the rule (e.g., '304.3.1')"),
  rule_description: string @description("Full description of the compliance rule"),
  question: string @description("The compliance check question"),

  // Training context (full details - these were used to create the tool)
  training_model_name: string @description("Name of the training model (e.g., 'duplex')"),
  training_expected_guids: string[] @description("GUIDs that should be found in training model"),
  training_predicted_guids: string[] @description("GUIDs that the tool actually found in training model"),
  training_tp: int @description("True positives on training data"),
  training_fp: int @description("False positives on training data"),
  training_fn: int @description("False negatives on training data"),
  training_f1: float @description("F1 score on training data"),

  // Validation context (ABSTRACT ONLY - no specific GUIDs to prevent leakage)
  validation_model_name: string @description("Name of the validation model (e.g., 'dental_clinic')"),
  validation_expected_count: int @description("Number of expected violations in validation model"),
  validation_predicted_count: int @description("Number of violations the tool found in validation model"),
  validation_tp: int @description("True positives on validation data"),
  validation_fp: int @description("False positives on validation data"),
  validation_fn: int @description("False negatives on validation data"),
  validation_f1: float @description("F1 score on validation data"),

  // Tool details
  tool_name: string @description("Name of the ACC tool function"),
  tool_implementation: string @description("Python source code of the tool"),
  execution_log: string @description("Execution log from running the tool on validation model (stdout, errors, etc.)"),

  // Retry context
  retry_count: int @description("Current retry attempt (0 = first attempt)"),
  previous_hints: string? @description("Previous improvement hints given (if any)")
) -> ACCToolAssessment {
  client GLM_4_7
  prompt #"
    You are an expert Python developer specializing in BIM (Building Information Modeling) compliance checking.

    Your task is to analyze why an ACC (Automated Code Compliance) tool performs differently on validation data compared to training data, and provide guidance for improvement.

    CRITICAL RULE: You must NOT include any validation-specific GUIDs, element names, or identifiers in your improvement_hint. This prevents information leakage that would cause overfitting.

    === COMPLIANCE RULE ===
    Rule: {{ rule_code }} - {{ rule_title }}
    Description: {{ rule_description }}
    Question: {{ question }}

    === TRAINING RESULTS ({{ training_model_name }}) ===
    Expected GUIDs: {{ training_expected_guids }}
    Predicted GUIDs: {{ training_predicted_guids }}
    Metrics: TP={{ training_tp }}, FP={{ training_fp }}, FN={{ training_fn }}, F1={{ training_f1 }}

    === VALIDATION RESULTS ({{ validation_model_name }}) - ABSTRACT ===
    NOTE: You only see counts, not specific GUIDs, to prevent overfitting.
    Expected count: {{ validation_expected_count }} violations
    Predicted count: {{ validation_predicted_count }} violations
    Metrics: TP={{ validation_tp }}, FP={{ validation_fp }}, FN={{ validation_fn }}, F1={{ validation_f1 }}

    === TOOL IMPLEMENTATION ===
    Function name: {{ tool_name }}
    ```python
    {{ tool_implementation }}
    ```

    === EXECUTION LOG ===
    {{ execution_log }}

    {% if previous_hints %}
    === PREVIOUS IMPROVEMENT ATTEMPTS ===
    Retry count: {{ retry_count }}
    Previous hints given:
    {{ previous_hints }}
    {% endif %}

    === YOUR ANALYSIS TASK ===

    1. **Compare Performance**: Analyze the gap between training F1 ({{ training_f1 }}) and validation F1 ({{ validation_f1 }})

    2. **Identify Root Cause**: Determine WHY the tool performs differently:
       - **overfitting**: Look for hardcoded values, specific element names, or patterns that only work for the training model
       - **missing_generalization**: Check if the tool misses certain element types, property variations, or edge cases
       - **implementation_bug**: Look for logic errors, incorrect calculations, or wrong IFC queries
       - **model_difference**: Consider if the validation model might have legitimate structural differences
       - **unknown**: If you cannot determine the cause

    3. **Formulate Improvement Hint**: Provide GENERIC guidance that could help improve the tool WITHOUT revealing validation specifics.

    GOOD improvement hints:
    - "Check for all IFC space classification types, not just 'Room'"
    - "Handle spaces with multiple boundary segments"
    - "Consider that wheelchair diameter calculation might need to check inner boundaries"
    - "Property names may vary - check both 'Name' and 'LongName' attributes"

    BAD improvement hints (DO NOT DO THIS):
    - "Check for space GUID 0ztdC3L1HAzhbhMHypqcVC" (leaks validation GUID)
    - "The dental_clinic has DRESS rooms that need checking" (leaks validation specifics)
    - "Space.-1.32 is being missed" (leaks validation element name)

    4. **Make Recommendation**:
       - **keep_tool**: If the tool is reasonably good (validation F1 >= 0.8) or you've exhausted improvement ideas
       - **retry_with_hint**: If you have a concrete improvement idea and retries remain

    === ANALYSIS PATTERNS ===

    **Signs of Overfitting:**
    - Training F1 = 1.0 but validation F1 much lower
    - Hardcoded element names or property values in code
    - Very specific queries that only match training model structure

    **Signs of Missing Generalization:**
    - Tool finds some violations but misses others (FN > 0)
    - Code only checks one property when multiple could indicate violations
    - Missing handling for certain IFC entity subtypes

    **Signs of Implementation Bug:**
    - Both training and validation have errors
    - Execution log shows exceptions or warnings
    - Logic errors visible in the code (wrong operators, incorrect thresholds)

    **Signs of Model Difference:**
    - Validation model may have different conventions (metric vs imperial, naming schemes)
    - Different IFC schema version or export settings
    - Legitimate structural differences that require different handling

    {{ ctx.output_format }}
  "#
}

// Test case: Tool overfits to training model
test ACCToolAssessorOverfittingTest {
  functions [ACCToolAssessor]
  args {
    rule_title "304_3_1_circular_space"
    rule_code "304.3.1"
    rule_description "Circular space shall have a diameter of 1.52 m (60 inches) minimum."
    question "What spaces in the current IFC model do not have enough room for wheelchair turning space?"
    training_model_name "duplex"
    training_expected_guids ["10mjSDZJj9gPS2PrQaxa3z", "10mjSDZJj9gPS2PrQaxa4o"]
    training_predicted_guids ["10mjSDZJj9gPS2PrQaxa3z", "10mjSDZJj9gPS2PrQaxa4o"]
    training_tp 2
    training_fp 0
    training_fn 0
    training_f1 1.0
    validation_model_name "dental_clinic"
    validation_expected_count 3
    validation_predicted_count 1
    validation_tp 1
    validation_fp 0
    validation_fn 2
    validation_f1 0.5
    tool_name "check_304_3_1_circular_space"
    tool_implementation #"
def check_304_3_1_circular_space(ifc_path: str) -> list[str]:
    import ifcopenshell
    model = ifcopenshell.open(ifc_path)
    violations = []
    for space in model.by_type('IfcSpace'):
        name = space.Name or ''
        if 'Room' in name or 'Stair' in name:
            # Check diameter
            # ... simplified
            violations.append(space.GlobalId)
    return violations
    "#
    execution_log "Execution completed. Found 1 violation."
    retry_count 0
    previous_hints null
  }
}

// Test case: Tool has implementation bug
test ACCToolAssessorBugTest {
  functions [ACCToolAssessor]
  args {
    rule_title "504_2_riser_height"
    rule_code "504.2"
    rule_description "Risers shall be 4 inches (100 mm) high minimum and 7 inches (180 mm) high maximum."
    question "What stairs have riser heights that do not meet requirements?"
    training_model_name "duplex"
    training_expected_guids ["0wkEuT1wr1kOyafLY4v_O1"]
    training_predicted_guids []
    training_tp 0
    training_fp 0
    training_fn 1
    training_f1 0.0
    validation_model_name "dental_clinic"
    validation_expected_count 0
    validation_predicted_count 0
    validation_tp 0
    validation_fp 0
    validation_fn 0
    validation_f1 1.0
    tool_name "check_504_2_riser_height"
    tool_implementation #"
def check_504_2_riser_height(ifc_path: str) -> list[str]:
    import ifcopenshell
    model = ifcopenshell.open(ifc_path)
    violations = []
    for stair in model.by_type('IfcStair'):
        riser_height = 0.18  # Wrong: hardcoded instead of extracted
        if riser_height < 0.1 or riser_height > 0.18:
            violations.append(stair.GlobalId)
    return violations
    "#
    execution_log "Execution completed. Found 0 violations."
    retry_count 0
    previous_hints null
  }
}
