// BAML template for BIM Information Extraction Evaluation
// Evaluates system responses using 3-category classification: Correct / Wrong / Abstained

enum QuestionCategory {
  Category1 @alias("1")
  Category2 @alias("2")
  Category3 @alias("3")
  Category4 @alias("4")
}



function EvaluateResponse(
  question: string,
  category: QuestionCategory,
  ground_truth: string,
  system_response: string,
) -> AnswerEvaluationResult {
  client GLM_4_6

  prompt #"
    You are evaluating a BIM information extraction system's response to a question.

    QUESTION CATEGORY: {{ category }}
    QUESTION: {{ question }}

    REFERENCE ANSWER: {{ ground_truth }}

    Note: This reference answer represents one valid answer from a human expert labeler,
    but is NOT absolute truth. The labeler may have:
    - Used different extraction methods (manual calculation, proxy measurements)
    - Made reasonable inferences not directly in the IFC model
    - Missed information that the system found
    - Applied domain knowledge or workarounds

    The system response may differ while still being correct.

    SYSTEM RESPONSE: {{ system_response }}

    ---

    EVALUATION TASK:

    Classify the system response as one of:
    - "correct": System provided accurate, useful answer
    - "wrong": System provided factually incorrect information
    - "abstained": System explicitly declined to answer

    ---

    CORE EVALUATION PRINCIPLE:

    Mark as WRONG only if the response contains factually incorrect information that
    contradicts verifiable facts from the reference answer or the IFC model.

    Different approaches, additional information, alternative extraction methods, or
    finding data the labeler missed are all ACCEPTABLE and should be marked CORRECT.

    ---

    EVALUATION CRITERIA:

    ALL CATEGORIES (1, 2, 3, 4):

    CORRECT if the response:
      * Core facts align with reference answer (different wording/structure is fine)
      * Provides ADDITIONAL accurate information beyond the reference (this is valuable, not hallucination)
      * Uses a different but valid extraction method and reaches reasonable conclusions
      * For geometric/computational questions: uses reasonable methodology and provides plausible results
      * Transparently explains data limitations or IFC model issues while still providing useful information
      * Finds information that the reference answer missed (the labeler may have been incomplete)
      * Makes stated assumptions that are reasonable for the context (especially Category 4)
      * Would be useful and non-misleading to a BIM professional

      Special considerations by category:
      - Category 1 (Direct Retrieval): Core facts should match, but additional context is beneficial
      - Category 2 (Computational): Allow ~5% numerical variance due to different calculation methods
      - Category 3 (Geometric): Multiple valid approaches exist (geometry-based vs property-based)
      - Category 4 (Incomplete Info): Transparency about limitations + useful partial answer is sufficient

    WRONG if the response:
      * Contains factual errors that directly CONTRADICT the reference answer on overlapping information
      * Fabricates specific data that is demonstrably not in the IFC model and contradicts reference
      * Provides incorrect numerical values that differ significantly (>5-10%) without explanation
      * Misidentifies elements, relationships, or properties in a way that contradicts reference
      * Makes unreasonable assumptions without stating them (Category 4)
      * Would mislead a BIM professional with false information

      Important: DO NOT mark as wrong if:
      - The response simply lacks some details from the reference (unless critical)
      - The response uses different extraction methods but is factually sound
      - The response provides more information than the reference
      - The response honestly states that certain data is not accessible in the IFC

    ABSTAINED if the response:
      * Explicitly refuses to answer with phrases like:
        - "I cannot determine..."
        - "Insufficient information to answer..."
        - "This data is not available and I cannot provide an answer..."
        - "I am unable to answer this question..."
        - "Cannot be calculated without..."

      DO NOT count as abstention:
      - Expressions of uncertainty while still providing an answer
      - Conditional statements ("If X, then Y...")
      - Partial information followed by explanation of limitations
      - "Data not found in standard properties, but here's what I found..."

    ---

    EVALUATION PROCESS:

    When the system response differs from the reference answer:

    1. Identify overlapping claims (what both answers address)
    2. Check if overlapping claims contradict each other factually
    3. If yes → Consider WRONG
    4. If no → Consider CORRECT (differences are acceptable)

    For additional information in system response not in reference:
    - Ask: "Is this plausibly derived from an IFC model?"
    - Ask: "Does this contradict the reference answer?"
    - If plausible and non-contradictory → CORRECT
    - If implausible or contradictory → WRONG

    ---

    IMPORTANT GUIDELINES:

    1. Compare semantic content, not exact wording or structure
    2. Multiple correct answers can exist, especially for Categories 3 & 4
    3. Additional accurate context is valuable, not problematic
    4. The reference answer may be incomplete or use undocumented methods
    5. Transparency about IFC model limitations is professional and appropriate
    6. Focus on: "Is this factually wrong?" not "Is this different from reference?"
    7. When in doubt between CORRECT and WRONG, prefer CORRECT if the response is useful and non-misleading

    {{ ctx.output_format }}
  "#
}

// Test function for EvaluateResponse
test radiator_count_test {
  functions [EvaluateResponse]
  args {
    question "How many radiator are there in room A202?"
    category Category1
    ground_truth "There is one radiator in room A202."
    system_response "I could find one radiator in room A202."
  }
}

// Test function for pipe types with additional context
// This tests whether additional contextual information is properly accepted
test pipe_types_with_context_test {
  functions [EvaluateResponse]
  args {
    question "What types of pipes are used in the building, including their quantities?"
    category Category1
    ground_truth "Total Pipe Segments: 60 Pipe Types: - hwa afvoer: 60 segments"
    system_response #"
      Based on my analysis of the IFC model, the building contains the following pipe-related elements:

      ## Main Pipe Types:

      ### 1. HWA Afvoer (Rainwater Drainage Pipes)
      - **Quantity**: 60 elements
      - **Type**: IfcBuildingElementProxy
      - **Material**: Zinc (04 Zink)
      - **Classification**: Pipe Segment
      - **Layer**: 5210_afvoeren - regenwater (rainwater drainage)
      - **Position**: Exterior
      - **Structural Function**: Non-Load-Bearing Element

      ### 2. Waterslag (Water Splash/Drip Edge)
      - **Quantity**: 35 elements
      - **Type**: IfcCovering
      - **Function**: Water management elements, typically installed at roof edges or transitions

      ## Summary:
      - **Total pipe-related elements**: 95
      - **Primary system**: Rainwater drainage (HWA system)
      - **Material**: All HWA pipes are made of zinc
      - **Location**: All exterior elements
      - **Modeling approach**: Pipes are modeled as IfcBuildingElementProxy elements rather than standard IfcPipe entities (due to IFC2X3 schema limitations)

      The building appears to have a comprehensive rainwater drainage system with 60 zinc pipe segments and 35 water splash protection elements, all designed for exterior installation and rainwater management.
    "#
  }
}
