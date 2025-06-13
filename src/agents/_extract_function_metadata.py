import ast
from pydantic import BaseModel


class PythonFunctionMetadata(BaseModel):
    name: str
    args: list = []
    defaults: list = []
    docstring: str = ""


def _extract_function_metadata(code: str, function_name: str) -> PythonFunctionMetadata:
    """
    Extract function metadata (name, signature, docstring) without executing the code.
    """
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                # Extract docstring
                docstring = ""
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                ):
                    docstring = node.body[0].value.value

                # Extract arguments
                args = []
                for arg in node.args.args:
                    args.append(arg.arg)

                # Extract defaults (simplified - just get their string representation)
                defaults = []
                for default in node.args.defaults:
                    if isinstance(default, ast.Constant):
                        defaults.append(repr(default.value))
                    else:
                        defaults.append("...")

                return PythonFunctionMetadata(
                    name=function_name,
                    args=args,
                    defaults=defaults,
                    docstring=str(docstring),
                )

    except Exception as e:
        return PythonFunctionMetadata(
            name=function_name,
            docstring=str(
                f"Function {function_name} - metadata extraction failed: {str(e)}"
            ),
        )


def return_blobed_name(name: str) -> str:
    """
    return the provided name blobed.
    """
    return name + "_blob"


if __name__ == "__main__":
    code = """

def return_blobed_name(name: str) -> str:
    '''
    return the provided name blobed.
    '''
    return name + "_blob"

    """
    function_name = "return_blobed_name"

    metadata = _extract_function_metadata(code=code, function_name=function_name)
    for key, value in metadata.dict().items():
        print(f"{key}: {value}")
