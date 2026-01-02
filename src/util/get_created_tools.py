"""Import all available tools"""

from typing import Callable, Dict, List

from src.util.get_logger import get_logger

logger = get_logger(__name__)


# Import all functions from each file
def get_created_tools(tools: List[Callable] = []) -> Dict[str, Callable]:  # type: ignore[assignment]
    """
    Return a Dict[str, Callable] with all the name and functions from:
    - the provided tools parameter
    - the functions in the tools/created directory

    DEPRECATED: Use get_tools(['created']) instead.
    Kept for backward compatibility with existing code.
    """
    from src.util.get_tools import get_tools_from_directory

    fn_dict: Dict[str, Callable] = {}

    # Add provided tools
    for fn in tools:
        fn_dict[fn.__name__] = fn  # type: ignore[attr-defined]

    # Add created tools
    created = get_tools_from_directory("created", allow_deletion=True)
    fn_dict.update(created)

    return fn_dict


def get_tools_description(tools: Dict[str, Callable] = {}) -> str:
    """Returns a serialised list of existing tools, along with their descriptions."""
    tools = tools or get_created_tools()
    tools_description = ""
    for fn_name, fn in tools.items():
        docstring = getattr(fn, "__doc__", "No description available.")
        # Clean up the docstring formatting and remove code blocks
        docstring_lines = []
        in_code_block = False
        for line in docstring.strip().split("\n"):
            line = line.strip()
            # Skip code block markers and content
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block:
                docstring_lines.append(line)

        docstring = " ".join(docstring_lines)
        tools_description += f"\n- `{fn_name}`: {docstring}"

    return tools_description


def get_tools_names(tools: Dict[str, Callable] = {}) -> str:
    """Returns a serialized list of existing tools names."""
    tools = tools or get_created_tools()
    tool_names = [fn_name for (fn_name, fn) in tools.items()]
    return ", ".join(tool_names)


if __name__ == "__main__":
    tools = get_created_tools()
    for name, fn in tools.items():
        # print(f"function's name: {name}\nfunction's docstring: {fn.__doc__}\n---\n")
        logger.info(f"function name: {name}")

    logger.info("/n/n")
    tools_description = get_tools_description()
    logger.info(tools_description)

    logger.info(get_tools_names())
