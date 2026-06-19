"""Render the IFC system prompt and the per-question human message.

Caching inversion (the key cobbie-specific change vs the sibling): the system
prompt is fully static across all questions in a cell. It depends only on the
two cell-level axes -- ``static`` (paradigm) and ``tools_docs`` (tools axis) --
never on the ifc path or the question text. That makes the system prefix
identical for every question in a cell and therefore cacheable, so we can
measure cached-input tokens. The per-question variables (ifc path, question)
go into the FIRST HUMAN MESSAGE via ``render_question_message``.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

_TEMPLATE_PATH = Path(__file__).parent / "system_prompt.jinja2"

# The shared answer-format section heading in the system prompt. Both arms hold
# answers to this same rubric: the agentic arm via the system prompt (and the
# Answer.text field description / _WRAP_UP_MSG echoing it), and the static arm's
# Phase-2 synthesis via extract_answer_format_section() below. Sourcing the
# static synthesis guidelines from the rendered prompt (not a hand-written copy)
# keeps the rubric identical across arms.
_ANSWER_FORMAT_HEADING = "# Answer format"


def extract_answer_format_section(system_prompt: str) -> str:
    """Return the canonical "# Answer format" section from a rendered system prompt.

    The static Phase-2 synthesis call reuses these exact guidelines (cite the
    IFC source per value, "Assuming [condition], [conclusion]" phrasing, metric
    SI, no tool-call XML / code fences / <think>) so static answers are held to
    the same rubric as the agentic arm. It slices from the "# Answer format"
    heading to the end of the prompt, which is the last section in the template.
    Raises if the heading is absent so a template change cannot silently drop
    the guidelines.
    """
    idx = system_prompt.find(_ANSWER_FORMAT_HEADING)
    if idx == -1:
        raise ValueError(
            f"{_ANSWER_FORMAT_HEADING!r} section not found in system prompt"
        )
    return system_prompt[idx:].strip()


def render_system_prompt(*, static: bool = False, tools_docs: str | None = None) -> str:
    """Render the static, cacheable system prompt for a cell.

    Args:
        static: ``True`` for the static (single-pass) paradigm variant, ``False``
            for the agentic (iterative) variant. Only changes the guidelines
            block (one call vs discovery loop); everything else is identical.
        tools_docs: When the tools arm is active, the formatted helper-function
            documentation to embed. ``None``/empty for the no-tools arm.

    The result contains no per-question variables, so it is byte-identical for
    every question in the cell (verify via the run_metadata prompt hash).
    """
    template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.render(static=static, tools_docs=tools_docs or "").strip() + "\n"


def render_question_message(*, ifc_path: str, question: str, tools: bool = False) -> str:
    """Render the first human message carrying the per-question variables.

    The ifc path lives here (not in the system prompt) so the system prefix
    stays static. In the tools arm the model object is preloaded as ``model``,
    so the message says so; otherwise the agent must open the model itself.
    """
    if tools:
        opening = (
            "The model has already been opened for you as `model` "
            "(an `ifcopenshell.file`) in the kernel namespace, loaded from the "
            f"path below. The curated helper functions are also preloaded.\n\n"
            f"IFC model path: {ifc_path}"
        )
    else:
        opening = (
            "Open the model yourself on your first `python_exec` call:\n"
            f"`import ifcopenshell; model = ifcopenshell.open({ifc_path!r})`\n\n"
            f"IFC model path: {ifc_path}"
        )
    return f"{opening}\n\nQuestion: {question}"
