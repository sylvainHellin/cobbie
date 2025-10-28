// BAML template for BIM Information Extraction Evaluation
// Evaluates system responses using 3-category classification: Correct / Wrong / Abstained

class QuestionCategory {
  category_1 @alias("1")
  category_2 @alias("2")
  category_3 @alias("3")
  category_4 @alias("4")
}

class EvaluationResult {
  classification string @description(#"
    One of: "correct", "wrong", or "abstained"
  "#)
  
  justification string @description(#"
    Brief explanation (2-3 sentences) of why this classification was chosen.
    For Category 4, explicitly mention whether assumptions were stated and reasonable.
  "#)
  
  confidence string @description(#"
    Evaluator confidence: "high", "medium", or "low"
  "#)
}

function evaluate_response(
  question: string,
  category: QuestionCategory,
  ground_truth: string,
  system_response: string,
  bim_context: string @description("Brief description of what data is available in the BIM model")
) -> EvaluationResult {
  client "anthropic/claude-3-7-sonnet-20250219"
  
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
    - CORRECT: Answer matches ground truth (factually accurate and complete)
    - WRONG: Answer contains factual errors or is incomplete
    - ABSTAINED: System explicitly declines (e.g., "I cannot determine...", "Insufficient information...")
    
    Category 4 (Incomplete Information):
    - CORRECT: Answer includes ALL of:
      1. Acknowledgment that some information is missing from BIM model
      2. Explicit statement of reasonable assumptions made
      3. No factual errors from BIM data
      4. Useful estimate or partial answer
      
    - WRONG: 
      - Missing assumptions (presents estimate as fact)
      - Unreasonable assumptions
      - Factual errors from BIM data
      - Hallucination of data not in model
      
    - ABSTAINED: System declined to answer (also acceptable for Category 4)
    
    SPECIAL HANDLING FOR "CANNOT BE DETERMINED" GROUND TRUTH:
    - If ground truth starts with "Cannot be determined:", this question is truly unanswerable
    - In this case: Any numerical/factual answer should be marked WRONG
    - Only abstention with explanation should be marked CORRECT (reclassify as "abstained" if appropriate)
    
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
    2. Allow for reasonable rounding/approximation in numerical answers
    3. For Category 4: Prioritize transparency about limitations over precision
    4. Be strict about hallucinations - any fabricated data should be marked WRONG
    5. Focus on whether the response would be useful and non-misleading to a BIM professional
    
    Return your evaluation as JSON with fields:
    - classification: "correct" | "wrong" | "abstained"
    - justification: Brief explanation (2-3 sentences)
    - confidence: "high" | "medium" | "low"
  "#
}

// Example usage template:
//
// client<llm> BimEvaluator {
//   provider "anthropic"
//   options {
//     model "claude-3-7-sonnet-20250219"
//     temperature 0.0  // Deterministic for consistency
//     max_tokens 500
//   }
// }
//
// Usage in code:
// result = evaluate_response(
//   question="What is the total embodied carbon of all windows?",
//   category=QuestionCategory.category_4,
//   ground_truth="Approximately 15,000 kg CO2e, assuming standard double-glazed units at 75 kg CO2e/m² and 200 m² total area from model. Note: Specific EPD data not in BIM model.",
//   system_response="Based on the 200 m² of windows in the model, and using standard EPD values for double-glazed units (75 kg CO2e/m²), the estimated embodied carbon is approximately 15,000 kg CO2e. Note: This assumes typical glazing systems as specific product EPDs are not available in the BIM model.",
//   bim_context="Model contains window geometries and quantities, but no specific Environmental Product Declaration (EPD) data for glazing products."
// )
