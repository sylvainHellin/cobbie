from typing import Any

from dspy import Signature

from .validate_type import validate_type


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
