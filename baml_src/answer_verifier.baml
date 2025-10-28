// BAML template for BIM Information Extraction Evaluation
// Evaluates system responses using 3-category classification: Correct / Wrong / Abstained

enum QuestionCategory {
  Category1 @alias("1")
  Category2 @alias("2")
  Category3 @alias("3")
  Category4 @alias("4")
}

class EvaluationResult {
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

function EvaluateResponse(
  question: string,
  category: QuestionCategory,
  ground_truth: string,
  system_response: string,
  bim_context: string @description("Brief description of what data is available in the BIM model")
) -> EvaluationResult {
  client ZAICodingPlan

  prompt #"
    You are evaluating a BIM information extraction system's response to a question.

    QUESTION CATEGORY: {{ category }}
    QUESTION: {{ question }}

    BIM CONTEXT: {{ bim_context }}

    GROUND TRUTH: {{ ground_truth }}

    SYSTEM RESPONSE: {{ system_response }}

    ---

    EVALUATION TASK:

    Classify the system response as one of:
    - "correct": System provided accurate answer
    - "wrong": System provided inaccurate/hallucinated answer
    - "abstained": System explicitly declined to answer

    EVALUATION CRITERIA BY CATEGORY:

    Categories 1, 2, 3 (Direct Retrieval, Computational, Geometric):
    - CORRECT: Answer matches ground truth (factually accurate and complete).     - ABSTAINED: System explicitly declines (e.g., "I cannot determine...", "Insufficient information...").

    Category 4 (Incomplete Information):
    - CORRECT: Answer includes ALL of:
      1. Acknowledgment that some information is missing from BIM model
      2. Explicit statement of reasonable assumptions made
      3. Useful estimate or partial answer
      4. There are no factual errors in the information extracted from the BIM model

    - WRONG:
      - Missing assumptions (presents estimate as fact)
      - Unreasonable assumptions
      - Hallucination of data not in model

    - ABSTAINED: System declined to answer (also acceptable for Category 4)

    ABSTENTION DETECTION:
    Look for explicit phrases indicating refusal:
    - "I cannot determine..."
    - "Insufficient information..."
    - "This data is not available..."
    - "I am unable to answer..."
    - "Cannot be calculated without..."

    Do NOT count as abstention:
    - Expressions of uncertainty while still providing an answer
    - Conditional statements ("If X, then Y")
    - Partial information followed by explanation

    IMPORTANT GUIDELINES:
    1. Compare semantic content, not exact wording
    2. Allow for reasonable rounding/approximation in numerical answers (e.g. 2%)
    3. For Category 4: Prioritize transparency about limitations over precision
    4. Be strict about hallucinations - any fabricated data should be marked WRONG
    5. Focus on whether the response would be useful and non-misleading to a BIM professional

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
    bim_context "this is the bim model for a duplex house."
  }
}
