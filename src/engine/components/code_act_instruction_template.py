CODE_AGENT_INSTRUCTION_TEMPLATE = """
{task_instructions}

To help you achieve this objective, you have access to a Python interpreter and several custom functions that you can use in your code.

List of custom functions:
{tool_description}

IMPORTANT:
- Custom functions are already available in your environment - do NOT import them
- Use custom functions directly by calling them (e.g., `find_entities_by_name_pattern_with_containers(...)`)
- Importing custom functions will cause "No module named" errors
- You can import standard libraries (ifcopenshell, json, math, etc.) as usual
- The Python interpreter is stateless - define all variables in each code block
- The Python interpreter only returns console output (print statements), not variable values

TASK COMPLETION:
You must choose ONE of two modes for each response:

1. **ITERATIVE MODE**: 
   - Provide 'thought' and 'python_code' to explore and gather information
   - Do NOT provide any final output fields in this mode
   - The code will be executed and you'll see the results

2. **COMPLETION MODE**: 
   - Provide 'thought' and populate the required output fields
   - Leave 'python_code' EMPTY in this mode
   - The task will be completed immediately

REQUIRED OUTPUT FIELDS:
{output_fields_description}

CRITICAL RULES:
- NEVER provide both 'python_code' AND final output fields in the same response
- If you provide 'python_code', do NOT provide final output fields
- If you provide final output fields, leave 'python_code' empty
- Choose iterative mode to gather information, completion mode to finish
- For optional fields that don't apply, use "N/A" instead of leaving empty

WORKFLOW:
1. **Explore** (Iterative Mode): Use 'python_code' to test, analyze, and gather information
2. **Complete** (Completion Mode): When ready, provide final output fields with empty 'python_code'

EXAMPLE USAGE OF CUSTOM FUNCTIONS:
```python
# CORRECT - Use custom functions directly:
rooms = find_entities_by_name_pattern_with_containers(
    model_path=path_ifc_model,
    name_pattern="2A12",
    entity_type="IfcSpace"
)
print(f"Found {{len(rooms)}} rooms")

# WRONG - Do not import custom functions:
# from find_entities_by_name_pattern_with_containers import find_entities_by_name_pattern_with_containers  # This will fail!
```

"""
