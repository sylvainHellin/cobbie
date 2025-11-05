// Category validation for BIM question-answer pairs
// Validates that questions are correctly categorized according to the 4-category taxonomy

function ValidateQuestionCategory(
  question: string,
  answer: string,
  current_category: string
) -> CategoryValidationResult {
  client GLM_4_6

  prompt #"
    You are a BIM dataset quality specialist responsible for validating question categorization according to a strict 4-category taxonomy.

    QUESTION: {{ question }}

    ANSWER: {{ answer }}

    CURRENT CATEGORY: {{ current_category }}

    ---

    TAXONOMY DEFINITIONS:

    **Category 1: Direct Information Retrieval**
    Tasks answerable through direct access to explicitly stored BIM element properties, regardless of the number of elements involved.

    Key characteristics:
    - Information is directly stored in BIM element properties
    - No calculations or derivations needed
    - Can involve single or multiple elements
    - Simple lookups or listings

    Examples:
    - "What is the width of the entrance door?"
    - "List all doors in the building"
    - "What material is used for wall W-101?"
    - "What types of windows are installed?"

    **Category 2: Computational Aggregation**
    Tasks requiring mathematical or logical operations (counting, averaging, filtering with conditions) on directly accessible data.

    Key characteristics:
    - Requires counting, summing, averaging, or filtering
    - Data is directly accessible, but needs aggregation
    - Involves logical operations or conditional filtering
    - No geometric/spatial calculations needed

    Examples:
    - "How many windows are there in the building?"
    - "What is the average thickness of all walls?"
    - "How many doors are on the second floor?"
    - "What is the total length of all pipes?"

    **Category 3: Geometric/Spatial Computation**
    Tasks requiring derived calculations from geometric or topological relationships not explicitly stored in the model.

    Key characteristics:
    - Requires geometric calculations (areas, volumes, distances)
    - Involves spatial relationships or topology
    - Needs derivation from geometric representations
    - May require complex spatial analysis

    Examples:
    - "What is the Gross Floor Area of the building?"
    - "What is the volume of room A202?"
    - "Which bedroom is closest to the main entrance?"
    - "What is the total surface area of all exterior walls?"

    **Category 4: Incomplete Information Scenarios**
    Tasks where complete accurate answers require information not available in the BIM model, potentially addressable through assumptions or external data.

    Key characteristics:
    - Requires information not typically stored in BIM models
    - May need external data sources or databases
    - Requires significant assumptions
    - Answer depends on data beyond geometric/property information

    Examples:
    - "What is the Global Warming Potential of this building?" (if GWP values not stored)
    - "What is the construction cost of the building?" (if cost data not included)
    - "What is the thermal transmittance of wall type A?" (if U-values not stored)
    - "How long will it take to construct this building?"

    ---

    CLASSIFICATION RULES:

    1. **If in doubt between two categories, choose the MORE DIFFICULT one:**
       - Between 1 and 2: Choose 2 (aggregation is more complex than retrieval)
       - Between 2 and 3: Choose 3 (geometric calculation is more complex than aggregation)
       - Between 3 and 4: Choose 4 (incomplete information is more challenging)

    2. **Distinguishing Category 1 vs 2:**
       - Category 1: "What types of pipes?" (listing) → Direct retrieval
       - Category 2: "How many types of pipes?" (counting) → Aggregation needed

    3. **Distinguishing Category 2 vs 3:**
       - Category 2: "How many walls are there?" (counting elements) → Simple aggregation
       - Category 3: "What is the total wall area?" (geometric calculation) → Spatial computation

    4. **Distinguishing Category 3 vs 4:**
       - Category 3: "What is the floor area?" (geometric, but derivable) → Spatial computation
       - Category 4: "What is the embodied carbon?" (needs external data) → Incomplete information

    5. **Questions asking for lists of values require aggregation:**
       - "List all door widths" → Category 2 (must collect/aggregate from multiple elements)
       - "What is the width of door D-101?" → Category 1 (single direct lookup)

    ---

    VALIDATION TASK:

    1. Analyze the question and answer to determine the correct category
    2. Compare with the current category
    3. If they match: set `updated` to false
    4. If they differ: set `updated` to true and provide the correct category
    5. Always provide clear reasoning in the `thought` field

    Be strict in your classification. When uncertain between two categories, always choose the more difficult one.

    {{ ctx.output_format }}
  "#
}

// Test: Category 1 - Direct retrieval (correctly classified)
test direct_retrieval_correct {
  functions [ValidateQuestionCategory]
  args {
    question "What is the width of the entrance door?"
    answer "The entrance door has a width of 900mm."
    current_category "1"
  }
}

// Test: Category 2 - Should be 2, but marked as 1 (misclassified)
test aggregation_misclassified {
  functions [ValidateQuestionCategory]
  args {
    question "How many windows are in the building?"
    answer "There are 45 windows in the building."
    current_category "1"
  }
}

// Test: Category 3 - Geometric computation (correctly classified)
test geometric_correct {
  functions [ValidateQuestionCategory]
  args {
    question "What is the Gross Floor Area of level 1?"
    answer "The Gross Floor Area of level 1 is 1,250.5 m²."
    current_category "3"
  }
}

// Test: Category 2 - List with aggregation (borderline case)
test list_aggregation {
  functions [ValidateQuestionCategory]
  args {
    question "What types of pipes are used in the building, including their quantities?"
    answer "Total Pipe Segments: 60\nPipe Types:\n- hwa afvoer: 60 segments"
    current_category "1"
  }
}

// Test: Category 4 - Incomplete information
test incomplete_information {
  functions [ValidateQuestionCategory]
  args {
    question "What is the Global Warming Potential of this building?"
    answer "The GWP cannot be determined as material carbon factors are not stored in the BIM model."
    current_category "4"
  }
}
