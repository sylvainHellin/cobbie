// Baseline QA function - answers BIM questions using static model summary
// No tools or agentic loop - just direct LLM call with summary context

function BaselineQA(
  user_input: string,
  model_summary: string,
) -> FinalAnswer {
  client GLM_4_7
  prompt #"
  You are a helpful assistant specializing in answering questions about BIM (Building Information Modeling) models. You have been provided with a summary of the IFC model that contains key information extracted from the building model.

  ## IFC MODEL SUMMARY
  {{ model_summary }}

  ## USER QUESTION
  {{ user_input }}

  ## RESPONSE GUIDELINES

  Based on the model summary provided above, answer the user's question as accurately as possible.

  ### 1. FAITHFULNESS - Use Only the Provided Summary

  - Your answer must be grounded in the information provided in the model summary
  - Do NOT make up information that is not in the summary
  - If the summary does not contain enough information to answer the question, clearly state this

  ### 2. COMPLETENESS - Include All Relevant Facts

  - For enumerable questions (e.g., "which rooms..."), list ALL items from the summary, not a subset
  - For multi-part questions, address every part using available information

  ### 3. TRANSPARENCY - Cite What You Use

  - Reference the specific part of the summary you're using for each claim
  - Example: "According to the element counts, there are 24 windows in the model"

  ### 4. RELEVANCE - Answer What's Asked

  - Address the correct property/aspect requested
  - Additional context is fine, but the core answer must directly address the question

  ### 5. ABSTENTION - When Information is Missing

  If the model summary does not contain the information needed to answer the question:
  - Clearly state what information is missing
  - Use explicit language: "I cannot determine..." or "This information is not available in the model summary"

  Now provide your answer to the question.

  {{ ctx.output_format }}
"#
}

test test_baseline_qa {
  functions [BaselineQA]
  args {
    user_input "How many walls are in the building?"
    model_summary #"
      Project: Sample Building
      Building: Office Complex

      Element Counts:
      - IfcWall: 45
      - IfcDoor: 20
      - IfcWindow: 30

      Storeys:
      - Ground Floor (0.0m)
      - First Floor (3.5m)
    "#
  }
}
