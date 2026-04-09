// Doc-augmented Static One-Shot
// Dedicated code generator that uses pre-fetched IfcOpenShell docs (no tools, no query_doc).
// Paired with shared StaticAnswerSynthesizer from static_oneshot.baml for answer synthesis.

// Planning agent -- identifies which IfcOpenShell APIs are needed
function DocQueryPlanner(
  user_input: string,
  model_path: string? @description("Path to the IFC model file, if available")
) -> DocQueryPlan {
  client GLM_4_7
  prompt #"
  You are a planning agent preparing to answer a question about a BIM model using Python and the IfcOpenShell library.

  You cannot write code yet. Your only job is to list up to 5 IfcOpenShell documentation query strings that cover the classes, methods, and patterns you will need to write Python code that answers the question. Be specific -- name the exact classes, methods, or module areas you expect to use.

  {% if model_path %}
  The IFC model is located at: {{ model_path }}
  {% endif %}

  Question: {{ user_input }}

  Produce a short reasoning (thoughts) explaining which IfcOpenShell APIs are relevant, then list up to 5 targeted query strings.

  {{ ctx.output_format }}
  "#
}


// Code generator with pre-fetched documentation context
function DocStaticCodeGenerator(
  user_input: string,
  model_path: string? @description("Path to the IFC model file, if available"),
  doc_context: string @description("Pre-fetched IfcOpenShell API documentation")
) -> CodeAction {
  client GLM_4_7
  prompt #"
  You are a BIM specialist. Write a single Python script using IfcOpenShell that answers the question below. Print all results to STDOUT.

  ## QUESTION
  {{ user_input }}

  {% if model_path %}
  ## IFC MODEL PATH
  {{ model_path }}
  {% endif %}

  ## CODE GUIDELINES
  - Use the IfcOpenShell API documentation provided below to write correct code.
  - Explore the model thoroughly: check relevant element types, properties, Psets, and quantity sets.
  - Match the specific element types, properties, and scope requested in the question.
  - Print results clearly so the answer can be synthesized from the output.
  - If information is unavailable, print what is available and note what is missing.

  ## RESPONSE QUALITY CRITERIA

  Your code output will be evaluated on these 5 criteria:

  ### 1. FAITHFULNESS - Source Hierarchy

  Use sources in this order of preference (always state which you're using):

  **Tier 1: Direct Retrieval** (Preferred)
  - Information directly from BIM element properties
  - Example: "The door width is 900mm (from property Door.Width)"

  **Tier 2: Simple Computation**
  - Unambiguous operations: counting, summing, averaging, filtering
  - Example: "There are 24 windows (counted from IfcWindow elements)"

  **Tier 3: Complex Computation**
  - Geometric/spatial calculations from coordinates, shapes, relationships
  - Example: "The room area is 45.2 m² (calculated from boundary geometry coordinates)"

  **Tier 4: Assumptions** (Use with caution)
  - When required information is missing from the model
  - You may make reasonable assumptions, but MUST:
    - State what information is missing
    - Explicitly declare the assumption: "Assuming X..."
    - Note that the answer is an estimate

  **Numerical Accuracy:**
  - Continuous measurements (lengths, areas, volumes): maintain precision to within 2%
  - Discrete counts (elements, rooms): must be exact

  ### 2. COMPLETENESS - Include All Relevant Facts

  - For enumerable questions (e.g., "which rooms..."), list ALL items, not a subset
  - For multi-part questions, address every part
  - If the data is insufficient, print what is available and note what is missing

  ### 3. TRANSPARENCY - Cite Every Claim

  Print the source or method for each piece of information in the output.

  ### 4. RELEVANCE - Answer What's Asked

  - Address the correct property/aspect requested
  - Address the correct scope (specific element vs. building-wide)

  ### 5. ABSTENTION - When to Refuse

  If required information is completely unavailable and no reasonable assumptions can be made, print a clear statement: "Cannot determine [X] as this information is not available in the BIM model."

  ## IFCOPENSHELL API REFERENCE
  {{ doc_context }}

  {{ ctx.output_format }}
"#
}


// Tests
test test_doc_query_planner {
  functions [DocQueryPlanner]
  args {
    user_input "How many walls are in the building?"
  }
}

test test_doc_static_code_generator {
  functions [DocStaticCodeGenerator]
  args {
    user_input "How many walls are in the building?"
    model_path "models/example.ifc"
    doc_context #"
## 1. ifcopenshell.file.by_type (ifcopenshell.file)
```python
def by_type(type: str, include_subtypes: bool = True) -> list[entity_instance]
```
Get all instances of a given IFC type from the model.
Returns a list of entity instances matching the requested type.
    "#
  }
}
