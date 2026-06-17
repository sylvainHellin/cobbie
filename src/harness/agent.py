"""IFC CodeAct harness: DeepAgent + persistent Jupyter kernel.

Ported from the sibling ``bim-query-comparison/pipelines/ifc/agent.py`` with
three cobbie-specific changes:

1. Static-prompt caching inversion. The system prompt is fully static across a
   cell (paradigm + tools axis only); the ifc path and question go in the first
   human message. This makes the system prefix cacheable and lets us measure
   cached-input tokens.
2. Static vs agentic paradigm. ``static=True`` caps the loop at exactly one
   code-generation+execution then forces synthesis (``StaticCapMiddleware`` with
   cap=1); ``static=False`` runs the normal agentic loop with the recursion
   guard. Same LLM, kernel, tool set, scaffolding -- the only difference is
   single-pass vs iterative.
3. Tools axis. In the tools arm the 15 curated helpers are preloaded into the
   kernel namespace (not registered as LangChain tools) and documented in the
   static system prompt.

Tracing is removed entirely (no MLflow/Phoenix). Token/latency/iteration
accounting comes straight from the LangChain result, including cached-input
tokens for the cost study.
"""

from __future__ import annotations

import re
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
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from src.harness.interpreter import JupyterInterpreter
from src.harness.llm import init_llm
from src.harness.prompts import render_question_message, render_system_prompt
from src.harness.tools_axis import build_preload_code, build_tools_docs

_TOOL_CALL_XML_RE = re.compile(r"<minimax:tool_call>.*?</minimax:tool_call>", re.DOTALL)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def sanitize_answer(text: str) -> str:
    """Strip model artifacts from the final answer.

    Removes (1) ``<think>...</think>`` reasoning blocks and (2) hallucinated
    ``<minimax:tool_call>`` XML emitted when tools are stripped at the static cap
    or recursion guard, so only the user-facing answer is stored and judged.
    """
    text = _THINK_BLOCK_RE.sub("", text)
    text = _TOOL_CALL_XML_RE.sub("", text)
    return text.strip()


_WRAP_UP_MSG = (
    "You have reached the exploration limit. Write your final answer now. "
    "Follow the answer format from your instructions: "
    "cite the IFC source for every value in parentheses, "
    "state any assumptions with 'Assuming [condition], [conclusion]', "
    "and if the information is not in the model, say so explicitly."
)


class RecursionGuardMiddleware(AgentMiddleware):
    """Force a wrap-up once the agent has taken too many steps (agentic arm).

    Counts AI messages in state as a step proxy. When the count reaches
    ``warn_after``, tools are stripped and a wrap-up HumanMessage is injected,
    forcing a text-only final answer that ends the loop.
    """

    def __init__(self, *, warn_after: int = 25) -> None:
        self._warn_after = warn_after

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
        if ai_count >= self._warn_after:
            request = request.override(
                tools=[],
                messages=[*request.messages, HumanMessage(content=_WRAP_UP_MSG)],
            )
        return handler(request)


class StaticCapMiddleware(AgentMiddleware):
    """Single-pass cap for the static paradigm.

    Allows exactly ``cap`` code-generation+execution rounds, then strips tools
    and injects the wrap-up message so the agent must synthesize its final
    answer from that one observation. With ``cap=1`` the agent gets one
    ``python_exec`` call and then a forced text answer.

    Implemented by counting AI messages: the first AI message carries the single
    tool call; once ``cap`` AI messages exist, the next model call has no tools.
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
            request = request.override(
                tools=[],
                messages=[*request.messages, HumanMessage(content=_WRAP_UP_MSG)],
            )
        return handler(request)


@dataclass
class AgentResult:
    """Normalized result from a single question run."""

    answer: str
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

    if static:
        middleware: list[AgentMiddleware] = [StaticCapMiddleware(cap=1)]
    else:
        middleware = [RecursionGuardMiddleware(warn_after=warn_after)]

    agent = create_deep_agent(
        model=llm,
        tools=[python_exec],
        system_prompt=system_prompt,
        middleware=middleware,
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
    answer = sanitize_answer(_normalize_content(messages[-1].content))
    if not answer:
        # Some models (e.g. MiniMax M2.7) emit only hallucinated tool-call XML
        # on the forced wrap-up turn, which sanitizes to empty. Fall back to the
        # last AI message that still carries real text after sanitizing.
        for msg in reversed(messages):
            if getattr(msg, "type", None) == "ai":
                candidate = sanitize_answer(_normalize_content(msg.content))
                if candidate:
                    answer = candidate
                    break
    trace_entries = _extract_trace(messages)
    in_tok, cached_tok, out_tok, tool_calls = _sum_usage(messages)

    return AgentResult(
        answer=answer,
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
    """Extract the code/observation transcript from the message history."""
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
            tool_calls = getattr(msg, "tool_calls", [])
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
            tool_calls += len(tc)
    return in_tok, cached_tok, out_tok, tool_calls
