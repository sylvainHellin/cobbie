"""Extract tool usage information from execution history.

This module provides utilities to parse execution histories and identify
which tools were called during question answering.

IMPORTANT: This expects the execution_history string specifically (the
iteration-by-iteration trace of code executions), NOT the full conversation
history. Passing the full conversation would cause false positives since
tools are listed in system prompts.
"""

import re
from typing import List


def extract_tools_used(execution_history: str, available_tools: List[str]) -> List[str]:
    """Extract tool names that were called in the execution history.

    Parses the execution history string (iteration-by-iteration trace) to find
    all function calls matching the pattern of tool names (lowercase with
    underscores). Only returns tools that are in the available_tools list.

    IMPORTANT: Pass execution_history (the previous_attempts accumulator from
    cobbie.py), NOT the full conversation history which includes system prompts.

    Args:
        execution_history: String containing the execution history with tool calls
            (the iteration-by-iteration trace, not full conversation)
        available_tools: List of tool names that are available (from tools_dict.keys())

    Returns:
        Deduplicated list of tool names that were called and exist in available_tools

    Examples:
        >>> history = "Called get_walls(ifc_file) and calculate_area(wall)"
        >>> available = ["get_walls", "calculate_area", "other_tool"]
        >>> extract_tools_used(history, available)
        ['get_walls', 'calculate_area']
    """
    # Regex pattern to match function calls: lowercase names with underscores
    pattern = r'\b([a-z_][a-z0-9_]*)\s*\('

    # Find all matches in the execution history
    potential_tools = re.findall(pattern, execution_history)

    # Filter to only tools that are in the available tools list
    existing_tools = [
        tool for tool in potential_tools
        if tool in available_tools
    ]

    # Return deduplicated list (preserving order of first occurrence)
    seen = set()
    deduplicated = []
    for tool in existing_tools:
        if tool not in seen:
            seen.add(tool)
            deduplicated.append(tool)

    return deduplicated
