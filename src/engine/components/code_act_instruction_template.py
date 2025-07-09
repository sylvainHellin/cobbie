# CodeAgent instruction template
CODE_AGENT_INSTRUCTION_TEMPLATE = """
solve a given task by writing and executing Python code.
For this, you have access to a Python interpreter to execute your code. In addition to standard Python built-in functions, you can also use the following custom tools:
{tool_description}

EXECUTION PATTERN:
1. **Think**: Analyze the user's request and your execution history (`trajectory`).
2. **Plan**: Formulate a plan to get closer to the solution.
3. **Code**: Write a Python code snippet to execute your plan.
4. **Repeat**: Repeat the process until the task is solved.

When you have collected all the necessary information, call the `final_answer()` function, packing the output fields into a dictionary and passing it as argument to the function. You don't need to import this function.

Task:
{task_instructions}

Expected outputs fields in `final_answer()` at the end of the task:
{output_fields_description}

IMPORTANT:
Your answer always need to be formated like in the example below. Any tool function you want to call needs to be inside of the [[ ## python_code ## ]]. The required output from the task need to be inside a dict, passed inside the `final_answer` function, INSIDE the [[ ## python_code ## ]]. Answer format:

[[## thought ##]]

[[ ## python_code ## ]]
"""
