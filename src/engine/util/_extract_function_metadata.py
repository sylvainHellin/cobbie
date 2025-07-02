import ast
from pydantic import BaseModel
import re


class PythonFunctionMetadata(BaseModel):
    name: str
    args: list = []
    defaults: list = []
    docstring: str = ""
    return_type: str = ""


def _extract_function_metadata(code: str, function_name: str) -> PythonFunctionMetadata:
    """
    Extract function metadata (name, signature, docstring) without executing the code.
    Tries to use AST parsing first, and falls back to regex for the docstring
    if the code contains syntax errors.
    """
    output = PythonFunctionMetadata(name=function_name)

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

                # Extract return type annotation
                return_type = ""
                if node.returns:
                    if isinstance(node.returns, ast.Name):
                        return_type = node.returns.id
                    elif isinstance(node.returns, ast.Constant):
                        return_type = str(node.returns.value)
                    elif isinstance(node.returns, ast.Attribute):
                        # Handle things like List[str], Dict[str, Any], etc.
                        return_type = ast.unparse(node.returns)
                    elif isinstance(node.returns, ast.Subscript):
                        # Handle generic types like List[str], Dict[str, Any]
                        return_type = ast.unparse(node.returns)
                    else:
                        return_type = ast.unparse(node.returns)

                output = PythonFunctionMetadata(
                    name=function_name,
                    args=args,
                    defaults=defaults,
                    docstring=str(docstring),
                    return_type=return_type,
                )

    except SyntaxError:
        # Fallback to regex if AST parsing fails
        docstring_match = re.search(
            rf'def\s+{function_name}\s*\(.*?\):\s*("""(.*?)"""|\'\'\'(.*?)\'\'\')',
            code,
            re.DOTALL | re.MULTILINE,
        )
        docstring = ""
        if docstring_match:
            docstring = (
                docstring_match.group(2)
                if docstring_match.group(2) is not None
                else docstring_match.group(3)
            )

        output = PythonFunctionMetadata(
            name=function_name,
            docstring=docstring.strip()
            if docstring
            else f"Could not parse docstring for {function_name} due to syntax errors.",
        )
    except Exception as e:
        output = PythonFunctionMetadata(
            name=function_name,
            docstring=str(
                f"Function {function_name} - metadata extraction failed: {str(e)}"
            ),
        )

    return output


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
