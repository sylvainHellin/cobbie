from typing import Callable, List, Optional, Type, Any, Literal
import typing

import dspy
from dspy.primitives.program import Module
from dspy.primitives.tool import Tool
from dspy.signatures.signature import Signature, ensure_signature
from smolagents.local_python_executor import LocalPythonExecutor, fix_final_answer_code
from smolagents.utils import parse_code_blobs

from src.engine.tools.primordial.python_interpreter import (
    AUTHORIZED_FUNCTIONS,
    AUTHORIZED_IMPORTS,
)


class CodeAgent(Module):
    """A dspy.Module that acts as a code-generating agent."""

    def __init__(
        self,
        signature: str | Type[Signature],
        tools: Optional[List[Callable]] = None,
        max_iters: int = 7,
    ):
        """
        Initializes the CodeAgent.

        Args:
            signature (str | Type[Signature]): The signature for the overall task,
                either as a string or a dspy.Signature class.
            tools (List[Callable], optional): A list of tools to make available
                to the Python interpreter.
            max_iters (int): The maximum number of code generation-execution loops.
        """
        super().__init__()
        self.signature = ensure_signature(signature)
        self.max_iters = max_iters

        def final_answer(answer: Any):
            """Marks the task as complete.
            Use this function when you are confident you have collected all the necessary information to answer the user's request.
            """
            return "Execution complete. The task is finished."

        self.tools = tools or []
        self.tools.append(final_answer)

        # Create a default interpreter if none is provided
        executor = LocalPythonExecutor(additional_authorized_imports=AUTHORIZED_IMPORTS)
        # Make provided tools available in the interpreter's scope
        tool_dict = AUTHORIZED_FUNCTIONS.copy()
        if self.tools:
            tool_dict.update({t.__name__: t for t in self.tools})
        executor.static_tools = tool_dict
        self.python_interpreter = executor

        self.python_interpreter_tool = Tool(
            func=self.python_interpreter,
            name="python_interpreter",
            desc="A tool to execute python code.",
        )

        # Build the tools description for the prompt
        tools_description = ""
        if self.tools:
            tools_description += "\nIn addition to standard Python built-in functions, you can also use the following custom tools:\n"
            for tool in self.tools:
                docstring = getattr(tool, "__doc__", "No description available.")
                # Clean up the docstring formatting
                docstring_lines = [
                    line.strip() for line in docstring.strip().split("\n")
                ]
                docstring = " ".join(docstring_lines)
                tools_description += f"- `{tool.__name__}`: {docstring}\n"

        # Build the output fields description
        output_fields_desc = []
        for name, field in self.signature.output_fields.items():
            type_info_str = ""
            if hasattr(field, "type") and field.type is not None:
                # Handle Literal types for clearer descriptions
                origin = typing.get_origin(field.type)
                if origin is Literal:
                    args = typing.get_args(field.type)
                    allowed_values = ", ".join(f"'{arg}'" for arg in args)
                    type_info_str = f" (must be one of: {allowed_values})"
                else:
                    # Fallback for other types
                    type_info_str = f" (type: {repr(field.type)})"

            desc_str = ""
            if hasattr(field, "desc") and field.desc:
                desc_str = f": {field.desc}"

            output_fields_desc.append(f"- `{name}`{type_info_str}{desc_str}")
        output_fields_str = "\n".join(output_fields_desc)

        # Internal signature for the generation loop
        code_gen_instr = f"""to execute a given task by writing and executing Python code.
For this, you have access to a Python interpreter to execute your code.

{tools_description}

You should always stick to the following pattern to execute the task:
1.  **Think**: Analyze the user's request and your execution history (`trajectory`).
2.  **Plan**: Formulate a plan to get closer to the solution.
3.  **Code**: Write a Python code snippet to execute your plan.
4.  **Repeat**: Repeat the process until the task is solved.

When you have collected all the necessary information, call the `final_answer()` function. You don't need to import this function.

Your ultimate goal is to collect enough information to provide the following outputs:
{output_fields_str}

Now, here the task you need to perform:
{self.signature.instructions}"""

        # The internal module for generating thought and code
        self.generate_code = dspy.Predict(
            dspy.Signature(
                {
                    **self.signature.input_fields,
                    "trajectory": dspy.InputField(
                        desc="Your execution history, consisting of your past thoughts, the code you wrote, and the execution results."
                    ),
                },
                instructions=code_gen_instr,
            )
            .append(
                "thought",
                dspy.OutputField(desc="Your reasoning and plan for the next step."),
            )
            .append(
                "python_code",
                dspy.OutputField(
                    desc="The Python code to execute to make progress on the task."
                ),
            )
        )

        # Module to extract the final answer from the trajectory
        extract_signature = self.signature.with_instructions(
            f"Given the execution trajectory, answer the original question.\n"
            f"Original Question: {self.signature.instructions}"
        ).insert(
            0,
            "trajectory",
            dspy.InputField(
                desc="The execution history of thoughts, code, and observations."
            ),
        )
        self.extract = dspy.ChainOfThought(extract_signature)

    def forward(self, **kwargs) -> dspy.Prediction:
        """
        Executes the CodeAgent's thought-code-execute loop.

        Args:
            **kwargs: Input fields defined in the user-provided signature.

        Returns:
            dspy.Prediction: An object containing the final answer.
        """
        trajectory: List[tuple[str, str, str]] = []

        for _ in range(self.max_iters):
            # Format trajectory for the prompt
            str_trajectory = ""
            for i, (thought, code, observation) in enumerate(trajectory):
                str_trajectory += f"---[Step {i + 1}]---\n"
                str_trajectory += f"Thought: {thought}\n"
                str_trajectory += f"Code:\n```python\n{code}\n```\n"
                str_trajectory += f"Observation: {observation}\n"
            if not str_trajectory:
                str_trajectory = "No execution history yet. This is the first step."

            # Generate thought and code
            prediction = self.generate_code(trajectory=str_trajectory, **kwargs)
            thought = prediction.get("thought", "")
            python_code = prediction.get("python_code", "")

            if not python_code:
                # If the model generates no code, assume it's stuck and break.
                observation = "The agent did not produce any code to complete the task."
                trajectory.append((thought, python_code, observation))
                break

            # Prepare and execute the code for intermediate steps
            try:
                code_blobs = parse_code_blobs(python_code)
                code_to_exec = fix_final_answer_code(code_blobs)
            except Exception as e:
                observation = f"Error parsing your code: {e}. Please make sure to format the code correctly in a ```python ... ``` block."
                trajectory.append((thought, python_code, observation))
                continue

            try:
                result, logs, is_final = self.python_interpreter_tool(
                    code_action=code_to_exec
                )
                observation = "Execution Logs:\n" + (logs or "No logs.")
                observation += "\n\nOutput:\n" + (repr(result) or "No output.")

                if is_final:
                    trajectory.append((thought, code_to_exec, observation))
                    break
            except Exception as e:
                observation = f"An error occurred during execution: {e}"

            trajectory.append((thought, code_to_exec, observation))

        # Format the final trajectory for the extraction module
        str_trajectory = ""
        for i, (thought, code, observation) in enumerate(trajectory):
            str_trajectory += f"---[Step {i + 1}]---\n"
            str_trajectory += f"Thought: {thought}\n"
            str_trajectory += f"Code:\n```python\n{code}\n```\n"
            str_trajectory += f"Observation: {observation}\n"

        # Use the extractor to produce the final answer
        prediction = self.extract(trajectory=str_trajectory, **kwargs)
        return prediction


if __name__ == "__main__":
    import uuid

    import mlflow

    from src.config import LANGUAGE_MODELS

    # 1. Define a simple tool
    def generate_uuid() -> str:
        """Generates a new universally unique identifier (UUID)."""
        return str(uuid.uuid4())

    # 2. Define the signature for the task
    class GenerateUUIDSignature(dspy.Signature):
        """Generates a new UUID and returns it."""

        task_description = dspy.InputField(
            desc="The user's request to generate a UUID."
        )
        generated_uuid = dspy.OutputField(desc="The newly generated UUID.")

    def main(lm_name: str = "gemini-flash"):
        # 3. Configure the language model
        lm_info = LANGUAGE_MODELS[lm_name]
        llm = dspy.LM(
            model=lm_info.url,
            api_key=lm_info.api_key,
            max_tokens=2000,
        )
        dspy.configure(lm=llm)

        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("CodeAgentTest")

        # 4. Instantiate the CodeAgent
        agent = CodeAgent(signature=GenerateUUIDSignature, tools=[generate_uuid])

        # 5. Run the agent
        task = "I need a new UUID."
        result = agent(task_description=task)

        # 6. Print the result and validate it
        print(f"Task: {task}")
        print(f"Generated UUID: {result.generated_uuid}")

        try:
            # Validate that the output is a valid UUID
            uuid.UUID(result.generated_uuid)
            print("Validation successful: The output is a valid UUID.")
        except (ValueError, TypeError, AttributeError):
            print("Validation failed: The output is not a valid UUID.")

    main()
