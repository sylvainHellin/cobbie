from typing import Optional
from src.config import FUNCTION_BOILERPLATE


def create_code_prefix(
    path_ifc_model: Optional[str],
    imports_boilerplate: Optional[str] = FUNCTION_BOILERPLATE,
) -> str:
    """
    Generates the Boilerplate code snippet.

    This function constructs a string containing the Boilerplate code,
    which is designed to be added as a prefix to Python code executed by CodeAct agents.

    Args:
        path_ifc_model (Optional[str]): The path to the IFC model.  If provided,
                                          it will be included in the Boilerplate string.
        imports_boiilerplate (Optional[str], optional):  A string containing import statements
                                                         for the Boilerplate. Defaults to
                                                         `FUNCTION_BOILERPLATE`.

    Returns:
        str: The generated Boilerplate code as a string.
             Returns an empty string if neither `path_ifc_model` nor
             `imports_boiilerplate` are provided.
    """

    if path_ifc_model is None and imports_boilerplate is not None:
        return imports_boilerplate + "\n"

    elif path_ifc_model is not None and imports_boilerplate is None:
        return f"path_ifc_model = '{path_ifc_model}'\n"

    elif path_ifc_model is not None and imports_boilerplate is not None:
        return imports_boilerplate + "\n" + f"path_ifc_model = '{path_ifc_model}'\n"

    else:
        return ""
