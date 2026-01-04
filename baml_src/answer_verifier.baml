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
  client GLM_4_7

  prompt #"
    You are evaluating a BIM information extraction system's response to a question using a multi-criteria assessment framework.

    QUESTION CATEGORY: {{ category }}
    QUESTION: {{ question }}

    REFERENCE ANSWER: {{ ground_truth }}

    Note: This reference answer represents one valid answer from a human expert labeler,
    but is NOT absolute truth. The system response may differ while still being correct.

    SYSTEM RESPONSE: {{ system_response }}

    ---

    ## QUESTION CATEGORIES (Background)

    Category 1 (Direct Retrieval): Direct information from BIM element properties, no computation
    Category 2 (Computational Aggregation): Simple unambiguous computations (counting, summing, averaging)
    Category 3 (Geometric/Spatial): Complex geometric computations from spatial relationships
    Category 4 (Incomplete Information): Required information not in model, may need assumptions

    ---

    ## EVALUATION WORKFLOW

    **Step 1: Determine if system ABSTAINED or PROVIDED AN ANSWER**

    ABSTAINED if response contains explicit refusal:
    - "I cannot determine..."
    - "Insufficient information to answer..."
    - "This data is not available and I cannot provide an answer..."
    - "I am unable to answer this question..."

    NOT abstained:
    - Expressions of uncertainty while providing answer
    - Conditional statements ("If X, then Y...")
    - Partial information with explanation of limitations

    **If ABSTAINED:**
    - Set abstention = true
    - Set ALL other criteria to 'Na'
    - Provide brief justification
    - STOP evaluation

    **If PROVIDED AN ANSWER:**
    - Set abstention = false
    - Proceed to evaluate 4 quality criteria independently

    ---

    ## CRITERION 1: FAITHFULNESS

    Are all claims grounded in valid sources for this question category?

    **Category-Specific Grounding Rules:**

    Category 1: BIM element properties ONLY
    - All values must exist directly in model
    - No computations permitted

    Category 2: BIM data + simple unambiguous computations
    - Computations: counting, summing, averaging, filtering
    - Must be deterministic

    Category 3: BIM geometry + complex geometric computations
    - May derive values not explicitly stored
    - Multiple valid calculation approaches acceptable

    Category 4: BIM data + computations + EXPLICITLY STATED assumptions
    - Assumptions MUST be disclosed verbatim in answer
    - "Assuming X..." or "Based on assumption that X..." required
    - Implied/hedged assumptions → FAIL

    **Numerical Tolerance:**

    For continuous measurements (lengths, areas, volumes):
    - Accept within 2% of reference answer
    - Formula: |system_value - ground_truth| / ground_truth ≤ 0.02

    For discrete counts (elements, rooms, floors):
    - Exact match required

    **Result:**
    - Yes: All claims grounded appropriately
    - No: Contains hallucinations, errors, or unstated assumptions (Cat 4)
    - Na: Only if abstention = true

    ---

    ## CRITERION 2: COMPLETENESS

    Are all relevant facts included to fully answer the question?

    **When to use 'Na':**
    - Question is open-ended ("describe", "explain") with no objective standard
    - Abstention occurred (mandatory)

    **When to use 'No':**
    - Answer omits critical facts for enumerable questions
    - Provides only subset of requested items (e.g., lists 2 of 4 adjacent rooms)
    - Partial answer to multi-part question

    **When to use 'Yes':**
    - All relevant facts present for enumerable questions
    - Reasonable detail level for open-ended questions

    **Result:**
    - Yes: Complete answer
    - No: Missing relevant facts
    - Na: Open-ended question OR abstention

    ---

    ## CRITERION 3: TRANSPARENCY

    Are sources/methods explicitly disclosed for each claim?

    **Passes transparency (Yes):**
    - "Width is 900mm from property Door.Width"
    - "24 windows counted from IfcWindow elements"
    - "Area is 245.8 m² calculated using ISO 9836"
    - "Assuming typical HVAC (20-25 year lifespan)..."

    **Fails transparency (No):**
    - "Width is 900mm" (no source)
    - "According to the model..." (too vague)
    - "Generally..." or "Typically..." (hedging, not explicit)

    Requirement: Every claim must cite specific property, method, or assumption.

    **Result:**
    - Yes: All claims have explicit source/method disclosure
    - No: Missing disclosure for any claim
    - Na: Only if abstention = true

    ---

    ## CRITERION 4: RELEVANCE

    Does the answer directly address the question asked?

    **Passes relevance (Yes):**
    - Addresses the correct aspect/property requested
    - Addresses correct scope (e.g., specific room vs. whole building)
    - May include additional information beyond question

    **Fails relevance (No):**
    - Answers wrong property (asked width, gave material)
    - Answers wrong scope (asked south facade, gave whole building)
    - Misunderstands question intent

    **Result:**
    - Yes: Directly addresses question
    - No: Off-topic or misunderstood question
    - Na: Only if abstention = true

    ---

    ## CRITICAL GUIDELINES

    1. **Evaluate criteria INDEPENDENTLY**: Do not let one judgment influence another
       - Faithful but incomplete is valid
       - Complete but unfaithful is valid
       - All combinations are possible

    2. **Use 'Na' sparingly**: Only for structural reasons (abstention, open-ended completeness)
       - NOT for uncertainty or difficulty judging
       - If unsure between Yes/No, choose based on best judgment and explain in justification

    3. **Focus justification on edge cases**:
       - Explain any 'No' verdicts
       - Explain borderline decisions
       - Keep to 2-3 sentences

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

// Test 3: Abstention case - system explicitly declines to answer
test abstention_test {
  functions [EvaluateResponse]
  args {
    question "What is the fire resistance rating of the walls?"
    category Category1
    ground_truth "Fire resistance data not available in model"
    system_response "I cannot determine the fire resistance rating as this information is not available in the IFC model."
  }
}

// Test 4: Numerical tolerance failure - exceeds 2% threshold
test numerical_tolerance_fail_test {
  functions [EvaluateResponse]
  args {
    question "What is the total floor area?"
    category Category2
    ground_truth "The total floor area is 500 m²"
    system_response "The total floor area is 520 m²"
  }
}

// Test 5: Complete but not transparent - no source disclosure
test no_transparency_test {
  functions [EvaluateResponse]
  args {
    question "How many windows are in the building?"
    category Category2
    ground_truth "There are 48 windows in the building"
    system_response "There are 48 windows"
  }
}

// Test 6: Category 4 unstated assumption - fails faithfulness
test unstated_assumption_test {
  functions [EvaluateResponse]
  args {
    question "What is the expected lifespan of the HVAC system?"
    category Category4
    ground_truth "Lifespan data not in model"
    system_response "Based on typical HVAC systems, the expected lifespan is 20-25 years"
  }
}

// Test 7: Category 4 explicit assumption - passes faithfulness
test explicit_assumption_test {
  functions [EvaluateResponse]
  args {
    question "What is the expected lifespan of the HVAC system?"
    category Category4
    ground_truth "Lifespan data not in model. Assuming typical commercial HVAC, 20-25 years."
    system_response "The lifespan data is not available in the model. Assuming typical commercial HVAC systems, the expected lifespan is 20-25 years."
  }
}

// Test 8: Incomplete enumeration - missing some adjacent rooms
test incomplete_enumeration_test {
  functions [EvaluateResponse]
  args {
    question "Which rooms are adjacent to room A101?"
    category Category1
    ground_truth "Rooms A102, A103, hallway, and stairwell are adjacent to A101"
    system_response "Rooms A102 and A103 are adjacent to A101"
  }
}

// Test 9: Irrelevant answer - answers wrong property
test irrelevant_answer_test {
  functions [EvaluateResponse]
  args {
    question "What is the width of door D101?"
    category Category1
    ground_truth "Door D101 has a width of 900mm"
    system_response "Door D101 is made of wood and has a fire rating of 30 minutes"
  }
}
