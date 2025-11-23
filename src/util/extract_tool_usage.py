"""Extract tool usage information from execution history.

This module provides utilities to parse execution histories and identify
which tools were called during question answering.

IMPORTANT: This expects the execution_history string specifically (the
iteration-by-iteration trace of code executions), NOT the full conversation
history. Passing the full conversation would cause false positives since
tools are listed in system prompts.
"""

import re
from pathlib import Path
from typing import List

from src.config import CREATED_TOOLS_PATH


def extract_tools_used(execution_history: str) -> List[str]:
    """Extract tool names that were called in the execution history.

    Parses the execution history string (iteration-by-iteration trace) to find
    all function calls matching the pattern of tool names (lowercase with
    underscores). Only returns tools that actually exist in the created tools
    directory.

    IMPORTANT: Pass execution_history (the previous_attempts accumulator from
    cobbie.py), NOT the full conversation history which includes system prompts.

    Args:
        execution_history: String containing the execution history with tool calls
            (the iteration-by-iteration trace, not full conversation)

    Returns:
        Deduplicated list of tool names that were called and exist in created tools

    Examples:
        >>> history = "Called get_walls(ifc_file) and calculate_area(wall)"
        >>> extract_tools_used(history)
        ['get_walls', 'calculate_area']  # assuming these tools exist
    """
    # Regex pattern to match function calls: lowercase names with underscores
    pattern = r'\b([a-z_][a-z0-9_]*)\s*\('

    # Find all matches in the execution history
    potential_tools = re.findall(pattern, execution_history)

    # Get path to created tools directory (absolute path from config)
    tools_dir = Path(CREATED_TOOLS_PATH)

    # Filter to only tools that exist as files in the created tools directory
    existing_tools = [
        tool for tool in potential_tools
        if (tools_dir / f"{tool}.py").exists()
    ]

    # Return deduplicated list (preserving order of first occurrence)
    seen = set()
    deduplicated = []
    for tool in existing_tools:
        if tool not in seen:
            seen.add(tool)
            deduplicated.append(tool)

    return deduplicated
