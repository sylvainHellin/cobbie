// Doc-augmented Static One-Shot: query documentation before generating code

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

// Tests
test test_doc_query_planner {
  functions [DocQueryPlanner]
  args {
    user_input "How many walls are in the building?"
  }
}
