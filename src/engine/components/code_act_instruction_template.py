# CodeAgent instruction template
#
# IMPROVEMENTS IMPLEMENTED:
# 1. Concise instructions following DSPy best practice of brevity for optimizer refinement
# 2. Clear structure with distinct sections (AVAILABLE FUNCTIONS, WORKFLOW, OUTPUT, etc.)
# 3. Simplified 3-step workflow (Think -> Code -> Iterate) vs. original 4-step
# 4. Direct, actionable language ("Solve tasks by writing...")
# 5. Complete format example showing proper final_answer usage
# 6. Reduced redundancy and clearer formatting requirements
# 7. Better alignment with CodeAct principle of iterative code execution
# 8. Added critical instruction about not importing available functions
#
CODE_AGENT_INSTRUCTION_TEMPLATE = """
Solve tasks by writing and executing Python code step-by-step.

AVAILABLE FUNCTIONS:
{tool_description}

IMPORTANT: Do NOT import these functions in your python_code - they are already available. Importing them will cause errors.

WORKFLOW:
1. **Think**: Analyze the task and your progress
2. **Code**: Write Python code to advance toward the solution
3. **Iterate**: Repeat until complete

OUTPUT: Call `final_answer(result_dict)` with all required fields when finished.

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
