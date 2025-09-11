CODE_AGENT_INSTRUCTION_TEMPLATE = """
{task_instructions}

To help you achieve this objective, you have access to a Python interpreter and several custom functions that you can use in your code.

List of custom functions:
{tool_description}

IMPORTANT:
You can use custom functions in your code without importing them. Importing them will cause errors. Do not import any of these custom functions.
The Python interpreter is stateless. This means that you need to define all the variables used in each block of generated code.
Check your result before returning your final answer with `final_answer`.

WORKFLOW:
1. **Think**: Analyze the task and your progress
2. **Code**: Write Python code to advance toward the solution
3. **Iterate**: Repeat until complete

OUTPUT:
Call `final_answer(result_dict)` with all required fields when finished.

REQUIRED FIELDS:
{output_fields_description}

"""
