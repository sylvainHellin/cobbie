CODE_AGENT_INSTRUCTION_TEMPLATE = """
Solve tasks by writing and executing Python code step-by-step.

AVAILABLE FUNCTIONS (do not import them):
{tool_description}

IMPORTANT: DO NOT import these functions in your python_code - they are already available. Importing them will cause errors.

WORKFLOW:
1. **Think**: Analyze the task and your progress
2. **Code**: Write Python code to advance toward the solution
3. **Iterate**: Repeat until complete

OUTPUT:
Call `final_answer(result_dict)` with all required fields when finished.

TASK:
{task_instructions}

REQUIRED FIELDS:
{output_fields_description}

RESPONSE FORMAT:
[[## thought ##]]
Brief reasoning for your next action

[[ ## python_code ## ]]
# Execute one logical step toward the solution
# Use final_answer({{key: value, ...}}) when ready

EXAMPLE:
[[## thought ##]]
I need to calculate the area and call final_answer with the result.

[[ ## python_code ## ]]
area = length * width
final_answer({{"calculated_area": area}})
"""
