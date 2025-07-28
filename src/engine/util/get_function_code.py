import os
from typing import Optional
from src.config import CREATED_TOOLS_PATH


def get_function_code(
    function_name: str,
    path: Optional[str] = None,
) -> Optional[str]:
    """
    Retrieve the source code for a dynamically created tool function.

    This utility function reads Python source code files containing tool functions
    that are typically generated and stored in the created tools directory. It's
    primarily used to load code for functions that can be executed dynamically
    in the IFC Answer Engine.

    Args:
        function_name (str): The name of the function to retrieve. If no path is
            provided, this will be used to construct the default file path as
            "{function_name}.py" in the created tools directory.
        path (Optional[str], optional): Custom file path to read the source code from.
            If None, defaults to the created tools directory using the function_name.
            Defaults to None.

    Returns:
        Optional[str]: The complete source code content of the file as a string,
            or None if the file cannot be read.

    Raises:
        FileNotFoundError: If the specified file path does not exist.
        IOError: If there are issues reading the file.

    Examples:
        >>> # Read code for a function using default path
        >>> code = get_function_code("get_interior_doors_count")
        >>> print(type(code))
        <class 'str'>

        >>> # Read code from a custom path
        >>> custom_path = "/path/to/my_function.py"
        >>> code = get_function_code("my_function", path=custom_path)

    Note:
        The default path construction assumes tool functions are stored as individual
        Python files in the CREATED_TOOLS_PATH directory, with the filename matching
        the function name followed by ".py".
    """
    code: Optional[str] = None

    if path is None:
        path = os.path.join(CREATED_TOOLS_PATH, f"{function_name}.py")

    with open(file=path, mode="r") as file:
        code = file.read()

    return code


if __name__ == "__main__":
    function_name = "get_interior_doors_count"
    code = get_function_code(function_name=function_name)
    print(code)
