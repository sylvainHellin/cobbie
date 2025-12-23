// Dataset cleaning utilities for aligning questions and answers

function QuestionAnswerAlignment(
  question: string,
  answer: string
) -> AlignedQAPair {
  client GLM_4_7

  prompt #"
    You are a dataset quality specialist focused on ensuring alignment between questions and answers in a BIM (Building Information Modeling) question-answering dataset.

    TASK: Analyze the question-answer pair and ensure they are properly aligned in structure, scope, and granularity.

    ORIGINAL QUESTION:
    {{ question }}

    ORIGINAL ANSWER:
    {{ answer }}

    ---

    ALIGNMENT PRINCIPLES:

    1. **Structural Alignment**: The question should clearly indicate the expected answer structure
       - If answer is a list, question should ask for "a list of..."
       - If answer is a count, question should ask "how many..."
       - If answer is a breakdown by category, question should request that breakdown

    2. **Scope Alignment**: The question scope should match what the answer provides
       - If answer covers specific types/categories, question should ask for those types/categories
       - Avoid ambiguous phrasings that could be interpreted differently than the answer provides

    3. **Granularity Alignment**: The level of detail should match
       - If answer provides "X per Y", question should ask for quantities "of each Y" or "by Y"
       - If answer is aggregate, question should ask for total/overall information

    4. **Clarity**: Both question and answer should be clear and professional
       - Questions can be rephrased for clarity while preserving intent
       - Answers can be formatted better (e.g., adding labels, structure) without changing facts

    CRITICAL CONSTRAINTS:
    - DO NOT modify, add, or remove any factual information from the answer
    - DO NOT change numerical values, element types, or technical details
    - DO NOT invent information not present in the original answer
    - If the pair is already well-aligned, return them unchanged (set was_modified to false)

    EXAMPLES OF GOOD ALIGNMENTS:

    Example 1 - List Structure:
    Original Q: "What types of pipes are used in the building, including their quantities?"
    Original A: "Total Pipe Segments: 60\nPipe Types:\n- hwa afvoer: 60 segments"

    Aligned Q: "Could you provide me with a list of the types of pipes used in the building and the quantities of each type?"
    Aligned A: "Total Pipe Segments: 60\nPipe Types:\n- hwa afvoer: 60 segments"
    Reason: Question now explicitly asks for "a list" and "quantities of each type", matching the answer structure

    Example 2 - Already Aligned:
    Original Q: "How many windows are on the ground floor?"
    Original A: "There are 12 windows on the ground floor."

    Aligned Q: "How many windows are on the ground floor?"
    Aligned A: "There are 12 windows on the ground floor."
    Reason: Already perfectly aligned, no changes needed

    Example 3 - Formatting Improvement:
    Original Q: "What are the room areas?"
    Original A: "Room A: 25.5 Room B: 30.2 Room C: 18.7"

    Aligned Q: "What are the areas of each room in the building?"
    Aligned A: "Room areas:\n- Room A: 25.5 m²\n- Room B: 30.2 m²\n- Room C: 18.7 m²"
    Reason: Question clarified, answer formatted for readability, no facts changed

    Now analyze the provided question-answer pair and produce an aligned version.

    {{ ctx.output_format }}
  "#
}

// Test with the pipes example
test stairs_alignment_test {
  functions [QuestionAnswerAlignment]
  args {
    question "What stair types are used, with their quantities?"
    answer #"
        Total Stairs: 71

   Stair Types:
   - 24_DD_ betontrap: 32 stairs (45.1%)
   - 24_stair_DD_trapbordes: 18 stairs (25.4%)
   - 24-DD-stalentrap verd: 14 stairs (19.7%)
   - Trap_DD-trap woning type F: 2 stairs (2.8%)
   - Trap_DD-trap woning type G: 2 stairs (2.8%)
   - 24-DD-stalen trap beganegrond: 1 stairs (1.4%)
   - 28_stair_DD_trapbordes: 1 stairs (1.4%)
   - DD-KOOILADDER: 1 stairs (1.4%)

   Concrete Stairs:
   - 24_DD_ betontrap: 32 stairs

   Steel Stairs:
   - 24-DD-stalen trap beganegrond: 1 stairs
   - 24-DD-stalentrap verd: 14 stairs

   Stair Landings:
   - 24_stair_DD_trapbordes: 18 landings
   - 28_stair_DD_trapbordes: 1 landings
    "#
  }
}

// Test with already aligned pair
test already_aligned_test {
  functions [QuestionAnswerAlignment]
  args {
    question "How many walls are in the building?"
    answer "There are 156 walls in the building."
  }
}
