import ast
from typing import Any

from dspy import Signature

from src.util.validate_type import validate_type


def check_final_answer(output: Any, signature: Signature) -> bool:
    """
    Check if the output from final_answer matches the expected signature output fields.

    Args:
        output: The output returned by final_answer
        signature: The signature to validate against

    Returns:
        bool: True if the output matches all expected output fields, False otherwise
    """
    if not isinstance(output, dict):
        try:
            output = ast.literal_eval(output)
        except Exception:
            return False

    output_fields = signature.output_fields  # type: ignore

    # Check that all required output fields are present
    for field_name, field in output_fields.items():
        if field_name not in output:
            return False

        # Validate the type of each field
        expected_type = field.annotation
        value = output[field_name]

        if not validate_type(value, expected_type):
            return False

    # Check that there are no extra fields (optional check)
    # Comment this out if you want to allow extra fields
    for key in output.keys():
        if key not in output_fields:
            return False

    return True


if __name__ == "__main__":
    import dspy
    from typing import cast

    class QA(dspy.Signature):
        """Answer the user's question"""

        question: str = dspy.InputField()
        answer: str = dspy.OutputField()

    class GenerateUUIDSignature(dspy.Signature):
        """Generates a new UUID and returns it."""

        task_description = dspy.InputField(
            desc="The user's request to generate a UUID."
        )
        generated_uuid = dspy.OutputField(desc="The newly generated UUID.")

    # last_output = {"generated_uuid": "24d6d214-9d85-418e-bbce-2ec263f9c268"}
    last_output = "{'answer': \"No, you don't need to take an umbrella tomorrow. The weather forecast for Munich shows sunny conditions with no rain.\"}"
    signature = cast(Signature, dspy.ensure_signature(QA))
    res = check_final_answer(output=last_output, signature=signature)
    print(res)
