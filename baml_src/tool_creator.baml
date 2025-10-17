// BAML ToolCreator implementation for replacing DSPy version
// Follows CodeAct pattern with union return types for clean flow control
// Reuses existing classes from schemas.baml

// Extended result class for when tool creation is complete
class FunctionImplementation {
  function_implementation string
  confidence float?
  needs_improvement bool
}

// Main ToolCreator function returning either continue action or final implementation
function ToolCreator(
  function_requirements: string,
  function_name: string,
  function_boilerplate: string,
  path_ifc_model: string,
  available_tools: string?,
  previous_attempts: string?
) -> CodeAction | FunctionImplementation {
  client ZAICodingPlan
  prompt #"
    You are an expert Python programmer specializing in creating tools for BIM (Building Information Modeling) analysis using the IfcOpenShell library.

    Your task is to create a new Python function based on the given requirements. The function must:

    1. Return proper data structures (e.g., lists and dictionaries), not formatted strings
    2. Be well-documented with docstrings and type hints
    3. Be explicit regarding assumptions (e.g., if using Revit-specific property sets)
    4. Follow proper Python error handling patterns

    {% if path_ifc_model %}
    IMPORTANT: The IFC model path for testing is: {{ path_ifc_model }}
    Use this exact path in your Python code when testing with IFC files.
    {% endif %}

    FUNCTION REQUIREMENTS:
    {{ function_requirements }}

    FUNCTION NAME: {{ function_name }}

    {% if function_boilerplate %}
    REQUIRED BOILERPLATE (must include at beginning):
    {{ function_boilerplate }}
    {% endif %}

    {% if available_tools %}
    AVAILABLE TOOLS:
    {{ available_tools }}
    {% endif %}

    {% if previous_attempts %}
    PREVIOUS ATTEMPTS:
    {{ previous_attempts }}
    {% endif %}

    You can either:
    1. Write Python code to create/test the function (returns CodeAction)
    2. Provide the final function implementation if complete (returns FunctionImplementation)

    Choose your next action:
    - CodeAction: If you need to write/execute Python code to develop the function
    - FunctionImplementation: If you have a complete, working function ready

    {{ ctx.output_format }}
  "#
}

// Fallback function to extract function implementation from conversation history
function CodeExtractor(
  function_name: string,
  conversation_history: string
) -> FunctionImplementation {
  client ZAICodingPlan
  prompt #"
    Extract the Python function implementation from the conversation history.

    Function name to extract: {{ function_name }}

    Conversation history:
    {{ conversation_history }}

    Find and return the complete Python function implementation including any imports, docstrings, and helper functions.

    {{ ctx.output_format }}
  "#
}

// Test function for ToolCreator
test ToolCreatorTest {
  functions [ToolCreator]
  args {
    function_requirements "Create a function that counts all walls in an IFC model. The function should take an IFC file path as input and return the total count as an integer."
    function_name "count_walls"
    function_boilerplate "import ifcopenshell\nimport typing\n"
    path_ifc_model "/path/to/test/model.ifc"
    available_tools #"
      def get_ifc_model_info(ifc_file_path: str) -> dict:
          '''Get basic information about an IFC model'''

      def web_search(query: str) -> str:
          '''Search the web for information'''
    "#
  }
}

test CodeExtractorTest {
  functions [CodeExtractor]
  args {
    function_name "count_walls"
    conversation_history #"
      User: Create a function to count walls
      Assistant: Here's the implementation:

      ```python
      import ifcopenshell
      from typing import List

      def count_walls(ifc_file_path: str) -> int:
          \"\"\"Count all wall elements in an IFC model.

          Args:
              ifc_file_path: Path to the IFC file

          Returns:
              Total number of wall elements
          \"\"\"
          model = ifcopenshell.open(ifc_file_path)
          walls = model.by_type('IfcWall')
          return len(walls)
      ```

      This function opens the IFC file and counts all IfcWall elements.
    "#
  }
}