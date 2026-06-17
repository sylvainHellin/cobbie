"""Tools axis: preload the curated helper library into the kernel namespace.

CodeAct purity: the helpers are ordinary callables placed in scope, not separate
LangChain tools. ``build_preload_code`` returns Python that imports the helpers
and opens the model as ``model``; ``build_tools_docs`` returns the signature +
one-line summary block embedded in the (static) system prompt so the agent knows
what is available.
"""

from __future__ import annotations

import inspect

from src.tools.curated import CURATED_TOOLS


def build_tools_docs() -> str:
    """Render a compact `name(signature)` + first-docstring-line list."""
    lines: list[str] = []
    for fn in CURATED_TOOLS:
        try:
            sig = str(inspect.signature(fn))
        except (ValueError, TypeError):
            sig = "(...)"
        doc = (fn.__doc__ or "").strip().splitlines()
        summary = doc[0].strip() if doc else ""
        lines.append(f"- `{fn.__name__}{sig}`: {summary}")
    return "\n".join(lines)


def build_preload_code(ifc_path: str) -> str:
    """Kernel preamble for the tools arm: imports + open model + common utils.

    Re-run after every ``reset()`` so each question in the cell starts from an
    identical preloaded namespace with a freshly opened model.
    """
    names = ", ".join(fn.__name__ for fn in CURATED_TOOLS)
    return (
        "import ifcopenshell\n"
        "import ifcopenshell.util.element\n"
        "import ifcopenshell.util.unit\n"
        f"from src.tools.curated import {names}\n"
        f"model = ifcopenshell.open({ifc_path!r})\n"
    )
