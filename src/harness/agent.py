"""IFC CodeAct harness: DeepAgent + persistent Jupyter kernel.

Ported from the sibling ``bim-query-comparison/pipelines/ifc/agent.py`` with
three cobbie-specific changes:

1. Static-prompt caching inversion. The system prompt is fully static across a
   cell (paradigm + tools axis only); the ifc path and question go in the first
   human message. This makes the system prefix cacheable and lets us measure
   cached-input tokens.
2. Static vs agentic paradigm. Both paradigms share one ``CapMiddleware(cap)``;
   ``static=True`` uses ``cap=1`` (exactly one code round, then a forced final
   answer), ``static=False`` uses ``cap=warn_after`` (iterative loop with a
   recursion guard). The two arms share the same agent construction, LLM,
   kernel, tool set, scaffolding, and ``response_format``. The treatment is
   operationalized by two things together: the integer cap and the
   paradigm-specific guidelines block in the system prompt (the
   ``{% if static %}`` branch rendered by ``render_system_prompt(static=...)``).
3. Tools axis. In the tools arm the 15 curated helpers are preloaded into the
   kernel namespace (not registered as LangChain tools) and documented in the
   static system prompt.

Tracing is removed entirely (no MLflow/Phoenix). Token/latency/iteration
accounting comes straight from the LangChain result, including cached-input
tokens for the cost study.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from deepagents import create_deep_agent
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.harness.interpreter import JupyterInterpreter
from src.harness.llm import init_llm
from src.harness.prompts import render_question_message, render_system_prompt
from src.harness.tools_axis import build_preload_code, build_tools_docs

# Injected on the cap turn alongside the forced Answer tool. The structural
# constraint (only the Answer tool is available) guarantees a parsed Answer
# object, but the model still needs the natural-language signal to STOP
# exploring and synthesize -- otherwise it dumps its intended next code call
# into Answer.text instead of an actual answer.
_WRAP_UP_MSG = (
    "Stop here. Do not request any more code execution. Using only what you "
    "have already observed, call the Answer tool now with your final answer. "
    "Put the complete user-facing answer in the 'text' field as natural-language "
    "prose (no code, no tool-call syntax): cite the IFC source for every value "
    "in parentheses, introduce every inference with 'Assuming [condition], "
    "[conclusion]', and if the information is not in the model, say so "
    "explicitly. Set 'sufficient_info' to whether the model had enough "
    "information to answer."
)


class Answer(BaseModel):
    """The final, user-facing answer to one IFC question.

    The agent emits this as a structured tool call instead of free text, which
    is what makes leaked ``<minimax:tool_call>`` XML or raw ```python blocks
    structurally impossible in the stored answer: the model can only ever pick
    the ``python_exec`` tool or this ``Answer`` tool, never plain message
    content. The loop ends the moment ``Answer`` is chosen.
    """

    text: str = Field(
        description=(
            "The complete natural-language answer for the user, following the "
            "answer-format guidance from the system prompt: cite the IFC source "
            "for every value in parentheses (e.g. 'NetFloorArea in "
            "Qto_SpaceBaseQuantities on IfcSpace #123'); introduce every "
            "inference with 'Assuming [condition], [conclusion]'; and if the "
            "information is genuinely not in the model, say so explicitly as a "
            "factual finding. Do not include tool-call XML, code fences, or "
            "<think> reasoning blocks -- only the answer prose."
        )
    )
    sufficient_info: bool = Field(
        description=(
            "True if the model contained enough information to answer the "
            "question; False if the answer had to abstain or report the "
            "information as not available after an exhaustive search."
        )
    )


# Structured-output tool name LangChain derives from the schema class name. Used
# to keep the forced final-answer turn out of the code/observation transcript.
_ANSWER_TOOL_NAME = Answer.__name__


class CapMiddleware(AgentMiddleware):
    """Cap the agent loop at ``cap`` code rounds, then force the structured answer.

    This integer ``cap`` is one of the two things that distinguish the two
    paradigms. The static and agentic arms share an identical agent construction
    -- same LLM, kernel, tool set, system scaffolding, and
    ``response_format=ToolStrategy(Answer)``. They differ in this cap and in the
    paradigm-specific guidelines block of the system prompt (the
    ``{% if static %}`` branch); the cap values are:

    - static:  ``cap=1``         -- one ``python_exec`` round, then a forced answer.
    - agentic: ``cap=warn_after`` -- iterate freely up to the recursion guard.

    Because ``response_format`` is set at agent-construction time, the factory
    binds the model with ``tool_choice="any"`` on every turn, so the model must
    always pick either ``python_exec`` or the ``Answer`` tool and can never emit
    free-form text (which is where MiniMax used to leak native tool-call XML).

    Once ``cap`` AI messages exist, this middleware overrides ``tools=[]`` for the
    next call. The factory still re-adds the structured ``Answer`` tool, so the
    model is left with exactly one legal move: emit ``Answer``. That ends the
    loop with a clean, parsed structured response.
    """

    def __init__(self, *, cap: int = 1) -> None:
        self._cap = cap

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | Any:
        ai_count = sum(
            1
            for m in request.state.get("messages", [])
            if getattr(m, "type", None) == "ai"
        )
        if ai_count >= self._cap:
            # Strip the exploration tools; the factory keeps the Answer tool and
            # forces tool_choice, so the only legal move is to emit Answer. Also
            # inject the wrap-up signal so the model synthesizes a real answer
            # instead of describing the next code call it would have run.
            request = request.override(
                tools=[],
                messages=[*request.messages, HumanMessage(content=_WRAP_UP_MSG)],
            )
        return handler(request)


@dataclass
class AgentResult:
    """Normalized result from a single question run."""

    answer: str
    structured: Answer | None = None
    trace: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    num_tool_calls: int = 0
    elapsed_s: float = 0.0


def create_ifc_agent(
    model: str,
    *,
    static: bool = False,
    tools: bool = False,
    max_retries: int = 3,
    warn_after: int = 25,
):
    """Create a CodeAct DeepAgent for one factorial cell.

    The system prompt is rendered once from the two cell axes (``static``,
    ``tools``) and is identical for every question in the cell. The same agent
    and interpreter are reused across questions; the caller resets the kernel
    between questions (see ``run_question``).

    Returns ``(agent, interpreter)``. The interpreter is also attached as
    ``agent._ifc_interpreter`` for convenience.
    """
    llm = init_llm(model, temperature=0, max_retries=max_retries)
    interp = JupyterInterpreter()

    @tool
    def python_exec(code: str) -> str:
        """Execute Python code in a persistent Jupyter kernel.

        Variables, imports, and loaded data persist across calls within a single
        question. Only stdout and stderr are returned -- use print() to see
        results.
        """
        return interp.run(code)

    tools_docs = build_tools_docs() if tools else None
    system_prompt = render_system_prompt(static=static, tools_docs=tools_docs)

    # static caps the loop at one code round, agentic at warn_after. The agent
    # construction (response_format included) is identical across paradigms; the
    # other half of the treatment is the paradigm-specific guidelines block,
    # already baked into system_prompt via render_system_prompt(static=...).
    cap = 1 if static else warn_after
    middleware: list[AgentMiddleware] = [CapMiddleware(cap=cap)]

    agent = create_deep_agent(
        model=llm,
        tools=[python_exec],
        system_prompt=system_prompt,
        middleware=middleware,
        response_format=ToolStrategy(Answer),
    )
    agent._ifc_interpreter = interp
    agent._system_prompt = system_prompt
    return agent, interp


def run_question(
    agent,
    interp: JupyterInterpreter,
    *,
    ifc_path: str,
    question: str,
    tools: bool = False,
    recursion_limit: int = 120,
) -> AgentResult:
    """Run a single question through the agent and return normalized results.

    The kernel is reset first (clean namespace). In the tools arm the curated
    helpers and the open ``model`` are preloaded into the namespace before the
    agent runs. Token usage (input/cached-input/output), tool-call count, and
    latency are extracted from the LangChain message history.
    """
    if tools:
        interp.preload(build_preload_code(ifc_path))
    else:
        interp.reset()

    human = render_question_message(ifc_path=ifc_path, question=question, tools=tools)
    config: dict = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "recursion_limit": recursion_limit,
    }
    input_msg = {"messages": [{"role": "user", "content": human}]}

    t0 = time.perf_counter()
    result = agent.invoke(input_msg, config=config)
    elapsed = time.perf_counter() - t0

    messages = result["messages"]
    # Primary path: the forced structured Answer. The agent loop only ends once
    # the model picks the Answer tool, so this is the user-facing answer.
    structured = result.get("structured_response")
    if isinstance(structured, Answer):
        answer = structured.text.strip()
    else:
        # Defensive guard, not a live path for current providers. With
        # tool_choice="any" the loop ends only by the model picking the Answer
        # tool (which sets structured_response, handled above) or by exceeding
        # recursion_limit, which raises and is recorded as an error row before
        # reaching here. So a returned result with no Answer does not occur
        # today; this falls back to the last AI message carrying text only if
        # some future provider ever returns without calling Answer.
        structured = None
        answer = _normalize_content(messages[-1].content)
        if not answer:
            for msg in reversed(messages):
                if getattr(msg, "type", None) == "ai":
                    candidate = _normalize_content(msg.content)
                    if candidate:
                        answer = candidate
                        break
    trace_entries = _extract_trace(messages)
    in_tok, cached_tok, out_tok, tool_calls = _sum_usage(messages)

    return AgentResult(
        answer=answer,
        structured=structured,
        trace=trace_entries,
        input_tokens=in_tok,
        cached_input_tokens=cached_tok,
        output_tokens=out_tok,
        num_tool_calls=tool_calls,
        elapsed_s=round(elapsed, 2),
    )


def _normalize_content(content) -> str:
    """Flatten LangChain message content (str or list of blocks) to a string."""
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        ).strip()
    return str(content).strip() if content else ""


def _extract_trace(messages) -> list[dict]:
    """Extract the code/observation transcript from the message history.

    The forced structured ``Answer`` tool call (and its synthetic tool message)
    is excluded: it is the final answer, not a CodeAct step, so it must not land
    in the steps table or inflate the iteration count.
    """
    entries: list[dict] = []
    step = 0
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "human":
            continue
        if msg_type == "ai":
            entry: dict = {"role": "assistant"}
            content = _normalize_content(msg.content)
            if content:
                entry["content"] = content
            tool_calls = [
                tc
                for tc in getattr(msg, "tool_calls", [])
                if tc.get("name") != _ANSWER_TOOL_NAME
            ]
            if tool_calls:
                tc_list = []
                for tc in tool_calls:
                    step += 1
                    tc_list.append(
                        {
                            "step": step,
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                        }
                    )
                entry["tool_calls"] = tc_list
            if content or tool_calls:
                entries.append(entry)
        elif msg_type == "tool":
            if getattr(msg, "name", "") == _ANSWER_TOOL_NAME:
                continue
            raw = msg.content if isinstance(msg.content, str) else str(msg.content)
            entries.append(
                {
                    "role": "tool",
                    "name": getattr(msg, "name", ""),
                    "content": raw,
                }
            )
    return entries


def _sum_usage(messages) -> tuple[int, int, int, int]:
    """Sum input/cached-input/output tokens and tool-call count across messages.

    Cached-input tokens come from ``usage_metadata['input_token_details']
    ['cache_read']`` (LangChain's normalized field for prompt-cache hits). When
    the provider does not report it, cached stays 0.
    """
    in_tok = 0
    cached_tok = 0
    out_tok = 0
    tool_calls = 0
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None)
        if usage and isinstance(usage, dict):
            in_tok += usage.get("input_tokens", 0)
            out_tok += usage.get("output_tokens", 0)
            details = usage.get("input_token_details") or {}
            if isinstance(details, dict):
                cached_tok += details.get("cache_read", 0) or 0
        tc = getattr(msg, "tool_calls", None)
        if tc:
            # The forced Answer tool call is the final answer, not a CodeAct
            # tool call; exclude it from the tool-call count.
            tool_calls += sum(
                1 for c in tc if c.get("name") != _ANSWER_TOOL_NAME
            )
    return in_tok, cached_tok, out_tok, tool_calls
