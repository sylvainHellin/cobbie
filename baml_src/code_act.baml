// BAML CodeAct implementation for BIM QA system
// Single function that returns either CodeAction (continue) or FinalAnswer (stop)

// Main BIM QA function with union return type
function BIMQAS(
  user_input: string,
  available_tools: string,
  previous_attempts: string? @description("Previous execution results, if any"),
  model_path: string? @description("Path to the IFC model file, if available")
) -> CodeAction | FinalAnswer {
  client ZAICodingPlan
  prompt #"
    You are a helpful assistant specialising in retrieving information from BIM models using Python code and the IfcOpenShell library. To facilitate this task, you also have access to higher-level functions that will help you with the most common information retrieval tasks (referred to later as the 'tools'). These tools can be used directly in your Python code as they are already pre-loaded; there is no need to import them.

    When a user asks a question, you can either:
    1. Write Python code to investigate further (returns CodeAction)
    2. Provide the final answer if you have sufficient information (returns FinalAnswer)

    {% if model_path %}
    IMPORTANT: The IFC model path is: {{ model_path }}
    Use this exact path in your Python code when calling IFC functions.
    {% endif %}

    Question:
    {{ user_input }}

    Tools:
    {{ available_tools }}

    {% if previous_attempts %}
    Previous Results:
    {{ previous_attempts }}
    {% endif %}

    Now, choose your next action (only one):
    - CodeAction: If you need to explore/analyze more with Python code
    - FinalAnswer: If you have enough information to answer completely

    {{ ctx.output_format }}
  "#
}

// Test function for BIMQAS
test bimqas_test {
  functions [BIMQAS]
  args {
    user_input "How many walls are in the building?"
    available_tools #"
      def count_walls() -> int:
          '''Count all wall elements in the IFC model'''

      def get_wall_materials(wall_guid: str) -> list:
          '''Get material information for a specific wall'''
    "#
  }
}
