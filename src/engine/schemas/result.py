from typing import Any, Callable, Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")  # For map operations


class Ok(Generic[T]):
    """Success variant of Result type, containing a value."""

    def __init__(self, value: T) -> None:
        self.value = value

    def is_ok(self) -> bool:
        """Check if this is a success result."""
        return True

    def is_err(self) -> bool:
        """Check if this is an error result."""
        return False

    def unwrap(self) -> T:
        """Get the success value. Safe to call when is_ok() is True."""
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Get the success value, or return default if this is an error."""
        return self.value

    def unwrap_err(self) -> Any:
        """Raises an exception. Don't call this on Ok."""
        raise RuntimeError(f"Called unwrap_err() on an Ok value: {self.value}")

    def map(self, func: Callable[[T], U]) -> "Result[U, Any]":
        """Apply a function to the success value if this is Ok."""
        try:
            return Ok(func(self.value))
        except Exception as e:
            return Err(str(e))

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


class Err(Generic[E]):
    """Error variant of Result type, containing an error."""

    def __init__(self, error: E) -> None:
        self.error = error

    def is_ok(self) -> bool:
        """Check if this is a success result."""
        return False

    def is_err(self) -> bool:
        """Check if this is an error result."""
        return True

    def unwrap(self) -> Any:
        """Raises an exception. Don't call this on Err - use unwrap_or() instead."""
        raise RuntimeError(f"Called unwrap() on an Err value: {self.error}")

    def unwrap_or(self, default: T) -> T:
        """Get the default value since this is an error."""
        return default

    def unwrap_err(self) -> E:
        """Get the error value. Safe to call when is_err() is True."""
        return self.error

    def map(self, func: Callable[[Any], U]) -> "Result[U, E]":
        """Return self unchanged since this is an error."""
        return self  # type: ignore

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


# Type alias for Result - this is the cleanest approach for typing
Result = Union[Ok[T], Err[E]]


# Convenience functions for creating Results
def ok(value: T) -> Ok[T]:
    """Create a success Result."""
    return Ok(value)


def err(error: E) -> Err[E]:
    """Create an error Result."""
    return Err(error)


# Type guard functions for better type narrowing
def is_ok(result: Result[T, E]) -> bool:
    """Type guard to check if result is Ok."""
    return result.is_ok()


def is_err(result: Result[T, E]) -> bool:
    """Type guard to check if result is Err."""
    return result.is_err()


# Example usage and testing
if __name__ == "__main__":

    def divide(a: int, b: int) -> Result[int, str]:
        if b == 0:
            return err("Cannot divide by zero")
        return ok(a // b)

    # Test success case
    result1 = divide(10, 2)
    print(f"10 / 2 = {result1}")
    if result1.is_ok():
        print(f"Success: {result1.unwrap()}")

    # Test error case
    result2 = divide(10, 0)
    print(f"10 / 0 = {result2}")
    if result2.is_err():
        print(f"Error: {result2.unwrap_err()}")

    # Test unwrap_or
    print(f"Safe division result: {result2.unwrap_or(-1)}")

    # Test map
    result3 = divide(20, 4).map(lambda x: x * 2)
    print(f"(20 / 4) * 2 = {result3}")

    print("Result type tests completed!")
