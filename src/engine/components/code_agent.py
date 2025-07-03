from typing import Callable, List, Optional, Type, Any

import dspy
from dspy.primitives.program import Module
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
        python_interpreter: Optional[Callable] = None,
        tools: Optional[List[Callable]] = None,
        max_iters: int = 7,
    ):
        """
        Initializes the CodeAgent.

        Args:
            signature (str | Type[Signature]): The signature for the overall task,
                either as a string or a dspy.Signature class.
            python_interpreter (Callable, optional): A callable Python interpreter.
                If not provided, a default LocalPythonExecutor will be created.
                The interpreter is expected to return a tuple: (result, logs, is_final).
            tools (List[Callable], optional): A list of tools to make available
                to the Python interpreter.
            max_iters (int): The maximum number of code generation-execution loops.
        """
        super().__init__()
        self.signature = ensure_signature(signature)
        self.max_iters = max_iters

        def finish(answer: Any):
            """Submits the final answer and concludes the task.

            Use this function when you are confident you have the correct and complete answer.
            The argument to this function will be returned as the final output.
            """
            return answer

        self.tools = tools or []
        self.tools.append(finish)

        if python_interpreter:
            self.python_interpreter = python_interpreter
        else:
            # Create a default interpreter if none is provided
            executor = LocalPythonExecutor(
                additional_authorized_imports=AUTHORIZED_IMPORTS
            )
            # Make provided tools available in the interpreter's scope
            tool_dict = AUTHORIZED_FUNCTIONS.copy()
            if self.tools:
                tool_dict.update({t.__name__: t for t in self.tools})
            executor.static_tools = tool_dict
            self.python_interpreter = executor

        # Build the tools description for the prompt
        tools_description = (
            "You have access to a Python interpreter to execute your code."
        )
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

        # Internal signature for the generation loop
        code_gen_instr = f"""You are a helpful and expert programmer.
Your goal is to solve the user's task by writing and executing Python code.

{tools_description}

**Strategy:**
1.  **Think**: Analyze the user's request and your execution history (`trajectory`).
2.  **Plan**: Formulate a plan to get closer to the solution.
3.  **Code**: Write a Python code snippet to execute your plan.
4.  **Repeat**: Repeat the process until the task is solved.

**Final Answer:**
When you have the final answer, call the `finish()` function with the final result as the only argument.
For example: `finish("this is my final answer")` or `finish(my_variable_containing_the_answer)`

Follow the user's instructions carefully.
{self.signature.instructions}"""  # type: ignore

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

    def forward(self, **kwargs) -> dspy.Prediction:
        """
        Executes the CodeAgent's thought-code-execute loop.

        Args:
            **kwargs: Input fields defined in the user-provided signature.

        Returns:
            dspy.Prediction: An object containing the final answer.
        """
        trajectory: List[tuple[str, str, str]] = []
        final_answer = None

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
                final_answer = "The agent did not produce any code to finish the task."
                break

            # Check if the agent wants to finish.
            if "finish(" in python_code:
                # Execute the final code to get the answer
                try:
                    result, logs, _ = self.python_interpreter(python_code)
                    final_answer = result
                except Exception as e:
                    final_answer = f"Error during final execution: {e}"
                break  # Exit the loop

            # Prepare and execute the code for intermediate steps
            try:
                code_blobs = parse_code_blobs(python_code)
                code_to_exec = fix_final_answer_code(code_blobs)
            except Exception as e:
                observation = f"Error parsing your code: {e}. Please make sure to format the code correctly in a ```python ... ``` block."
                trajectory.append((thought, python_code, observation))
                continue

            try:
                result, logs, is_final = self.python_interpreter(code_to_exec)
                observation = "Execution Logs:\n" + (logs or "No logs.")
                observation += "\n\nOutput:\n" + (repr(result) or "No output.")

                if is_final:
                    final_answer = result
                    break
            except Exception as e:
                observation = f"An error occurred during execution: {e}"

            trajectory.append((thought, code_to_exec, observation))

        # Create a dspy.Prediction object with the final answer.
        # This mirrors how dspy.ReAct returns its results.
        if final_answer is not None:
            # We assume the signature has a single output field for simplicity,
            # but this can be extended.
            output_field_name = list(self.signature.output_fields.keys())[0]
            return dspy.Prediction(**{output_field_name: final_answer})
        else:
            # If the loop finishes without a final answer, return an empty Prediction
            # or handle the error as appropriate.
            # Returning an empty prediction to avoid breaking dspy chains.
            return dspy.Prediction(
                **{k: None for k in self.signature.output_fields.keys()}
            )


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
