"""Tools documentation generation utilities for COBBIE and other components."""

import inspect
from typing import Callable, Dict, List

from loguru import logger


def generate_tools_docs(tools: Dict[str, Callable]) -> str:
    """
    Generate tool documentation for prompts from a dictionary of tools.
    
    Args:
        tools: Dictionary mapping tool names to callable functions
        
    Returns:
        Formatted string containing documentation for all tools
    """
    if not tools:
        return "No tools available."
    
    docs = []
    
    for name, tool in tools.items():
        if callable(tool):
            try:
                # Get function signature
                sig = inspect.signature(tool)
                
                # Get docstring
                docstring = inspect.getdoc(tool) or "No documentation available"
                
                # Clean up docstring formatting
                clean_docstring = _clean_docstring(docstring)
                
                # Format tool documentation
                tool_doc = f"def {name}{sig}:\n    '''{clean_docstring}'''"
                docs.append(tool_doc)
                
            except Exception as e:
                logger.warning(f"Could not generate docs for {name}: {e}")
                docs.append(f"def {name}():\n    '''Documentation generation failed'''")
        else:
            docs.append(f"def {name}():\n    '''Not callable'''")
    
    return "\n\n".join(docs)


def generate_tools_docs_from_list(tools: List[Callable]) -> str:
    """
    Generate tool documentation for prompts from a list of tools.
    
    Args:
        tools: List of callable functions
        
    Returns:
        Formatted string containing documentation for all tools
    """
    if not tools:
        return "No tools available."
    
    # Convert list to dictionary using function names
    tools_dict = {}
    for tool in tools:
        if callable(tool):
            name = getattr(tool, '__name__', f'tool_{len(tools_dict)}')
            tools_dict[name] = tool
    
    return generate_tools_docs(tools_dict)


def _clean_docstring(docstring: str) -> str:
    """
    Clean up docstring formatting for prompt usage.
    
    Args:
        docstring: Raw docstring from function
        
    Returns:
        Cleaned docstring suitable for prompts
    """
    if not docstring:
        return "No documentation available"
    
    docstring_lines = []
    in_code_block = False
    
    for line in docstring.strip().split("\n"):
        line = line.strip()
        
        # Skip code block markers
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        
        # Skip empty lines inside code blocks
        if in_code_block and not line:
            continue
            
        # Add non-empty lines
        if line:
            docstring_lines.append(line)
    
    # Join lines with spaces for better prompt formatting
    cleaned = " ".join(docstring_lines) if docstring_lines else "No documentation available"
    
    # Limit length for prompt efficiency
    if len(cleaned) > 500:
        cleaned = cleaned[:497] + "..."
    
    return cleaned


def get_tool_summary(tools: Dict[str, Callable]) -> str:
    """
    Generate a brief summary of available tools.
    
    Args:
        tools: Dictionary mapping tool names to callable functions
        
    Returns:
        Brief summary string
    """
    if not tools:
        return "No tools available."
    
    tool_names = list(tools.keys())
    if len(tool_names) <= 5:
        return f"Available tools: {', '.join(tool_names)}"
    else:
        return f"Available tools: {', '.join(tool_names[:5])}... ({len(tool_names)} total)"


def validate_tools(tools: Dict[str, Callable]) -> List[str]:
    """
    Validate tools and return list of issues.
    
    Args:
        tools: Dictionary mapping tool names to callable functions
        
    Returns:
        List of validation issues
    """
    issues = []
    
    for name, tool in tools.items():
        # Check if callable
        if not callable(tool):
            issues.append(f"Tool '{name}' is not callable")
            continue
            
        # Check if function has proper name
        if not hasattr(tool, '__name__'):
            issues.append(f"Tool '{name}' has no __name__ attribute")
            
        # Try to get signature
        try:
            inspect.signature(tool)
        except Exception as e:
            issues.append(f"Tool '{name}' signature error: {e}")
    
    return issues