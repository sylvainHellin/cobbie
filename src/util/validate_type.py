from typing import Any, Union, Type, get_origin, get_args


def validate_type(value: Any, expected_type: Type) -> bool:
    """
    Validate if a value matches the expected type, including handling Literal types.

    Args:
        value: The value to validate
        expected_type: The expected type annotation

    Returns:
        bool: True if the value matches the expected type, False otherwise
    """
    # Handle None type
    if expected_type is type(None) or expected_type.__class__.__name__ == "NoneType":
        return value is None

    # Handle Literal types
    origin = get_origin(expected_type)
    if origin is not None:
        # Check for Literal types
        if hasattr(origin, "__name__") and origin.__name__ == "Literal":
            # For Literal types, check if the value is one of the allowed literal values
            literal_values = get_args(expected_type)
            return value in literal_values

        # Handle Union types (including Optional which is Union[T, None])
        if origin is Union:
            union_args = get_args(expected_type)
            return any(validate_type(value, arg) for arg in union_args)

    # Handle basic types
    try:
        if hasattr(expected_type, "__origin__"):
            # This is a generic type, get the origin
            origin_type = get_origin(expected_type)
            if origin_type is not None:
                return isinstance(value, origin_type)
            else:
                # If origin is None, fall back to regular type check
                return isinstance(value, expected_type)
        else:
            # Regular type check with special handling for bool/int ambiguity
            if expected_type is int and isinstance(value, bool):
                # bool is a subclass of int in Python, but we want to be strict here
                # If we're expecting int specifically, don't allow bool
                return False
            return isinstance(value, expected_type)
    except (TypeError, AttributeError):
        # Fallback: if we can't determine the type, assume it's invalid
        return False
