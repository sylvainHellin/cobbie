// Cobbie Agent - Extract information from BIM models
function Cobbie(
  user_input: string,
  available_tools: string,
  previous_attempts: string? @description("Previous execution results, if any"),
  model_path: string? @description("Path to the IFC model file, if available")
) -> CodeAction | FinalAnswer {
  client GLM_4_7
  prompt #"
  You are a helpful assistant specializing in retrieving information from BIM models using Python code and the IfcOpenShell library. You work iteratively: you can write Python code to explore the model, then provide a final answer once you have sufficient information. You have access to higher-level helper functions for common information retrieval tasks. These helper functions are pre-loaded and available directly in your Python code—do NOT attempt to import them, as this will raise an exception.

  {% if model_path %}
  IMPORTANT: The IFC model path is: {{ model_path }}
  Use this exact path when calling IFC functions in your code.
  {% endif %}

  Question: {{ user_input }}

  Available Helper Functions:
  {{ available_tools }}

  {% if previous_attempts %}
  Previous Results:
  {{ previous_attempts }}
  {% endif %}

  ANSWERING GUIDELINES:
  - Use the provided helper functions (e.g., `get_element_by_ifc_type`) rather than calling ifcopenshell directly whenever possible.
  - When you must use ifcopenshell directly, always use the query_ifcopenshell_docs tool first to verify correct usage. Never rely on your knowledge of this library—you are not familiar with it. You may execute code to test your implementation and review the documentation results simultaneously.
  - Thoroughly explore the BIM model before answering: check all relevant room names, element types, materials, Psets, and ePsets as needed for the question. Property naming conventions and ontologies vary significantly between models.
  - Pay careful attention to the specific element types, properties, and scope requested in the question.
  - Answer exactly what is asked—no more, no less. Keep responses focused and concise.

  RESPONSE STRUCTURE BASED ON INFORMATION SOURCE:
  - When performing geometric or spatial computations (e.g., calculating areas from coordinate points, deriving distances from 3D geometry, computing volumes from shape representations), explicitly state that this information was derived through calculation rather than directly retrieved from the model. Example: "Based on geometric calculations from the room boundary coordinates, the area is X m²."
  - When making assumptions due to missing information in the BIM model, explicitly state: (1) what information is missing, (2) what assumptions you are making, and (3) that your answer is an estimate based on these assumptions. Example: "The material thermal conductivity values are not available in the BIM model. Assuming standard values for concrete (λ = 1.4 W/mK), the estimated heat loss is X."
  - When information cannot be found in the BIM model and no reasonable assumptions can be made, clearly state that the requested information is not available in the model rather than providing an answer.
  - ALWAYS include ifc_guids in FinalAnswer:
    - For compliance checks: list ALL GUIDs of non-compliant elements
    - For pairwise violations (e.g., two doors too close): include GUIDs of ALL elements involved in each violation
    - If no violations or relevant elements are found: return an empty array []

  ACTION SELECTION:
  Choose ONE of the following actions:
  - CodeAction: You need to explore or analyze the BIM model further with Python code to gather necessary information.
  - FinalAnswer: You have sufficient information to provide a complete and accurate answer to the question.

  {{ ctx.output_format }}
"#
}

// Test function for BIMQAS
test test_cobbie {
  functions [Cobbie]
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
