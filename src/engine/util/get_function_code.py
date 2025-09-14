import os
from typing import Optional
from src.config import CREATED_TOOLS_PATH
from src.engine.schemas import Result, ok, err, Err


def get_function_code(
    function_name: str,
    path: Optional[str] = None,
) -> Result[str, str]:
    """
    Retrieve the source code for a dynamically created tool function.

    Args:
        function_name (str): The name of the function to retrieve.
        path (Optional[str], optional): Custom file path to read the source code from.
            If None, defaults to the created tools directory using the function_name.
            Defaults to None.

    """
    try:
        if path is None:
            path = os.path.join(CREATED_TOOLS_PATH, f"{function_name}.py")

        with open(file=path, mode="r") as file:
            code = file.read()

        return ok(code)

    except Exception as e:
        return err(error=str(e))



if __name__ == "__main__":
    function_name = "get_interior_doors_count"
    code = get_function_code(function_name=function_name)
    print(code)

    function_name = "check_fire_rating"
    code = get_function_code(function_name)
    print(code)
