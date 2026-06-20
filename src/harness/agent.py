"""IFC CodeAct harness: DeepAgent + persistent Jupyter kernel.

Ported from the sibling ``bim-query-comparison/pipelines/ifc/agent.py`` with
three cobbie-specific changes:

1. Static-prompt caching inversion. The system prompt is fully static across a
   cell (paradigm + tools axis only); the ifc path and question go in the first
   human message. This makes the system prefix cacheable and lets us measure
   cached-input tokens.
2. Static vs agentic paradigm. They differ in their generation path. The
   agentic arm is a single tool-calling agent: ``CapMiddleware(cap=warn_after)``
   iterates freely up to a recursion guard, then forces a structured final
   answer (``response_format=ToolStrategy(Answer)`` + wrap-up injection). The
   static arm is a two-call pipeline (see ``run_question``): Phase 1 runs
   exactly one ``python_exec`` round and stops (``StaticOneRoundMiddleware``,
   no forced Answer, no wrap-up); Phase 2 is a SEPARATE plain
   ``init_llm(...).invoke(...)`` completion that synthesizes the final
   natural-language answer from {question + ifc context + Phase-1 code +
   Phase-1 observation + the shared answer-format guidelines}. Separating the
   answer-producing turn from the tool-calling turn is what prevents the static
   arm leaking raw tool-call markup into the answer. Both arms share the same
   LLM, kernel, tool set, scaffolding, and the paradigm-specific guidelines
   block in the system prompt (the ``{% if static %}`` branch rendered by
   ``render_system_prompt(static=...)``).
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
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.harness.interpreter import JupyterInterpreter
from src.harness.llm import init_llm
from src.harness.prompts import (
    extract_answer_format_section,
    render_question_message,
    render_system_prompt,
)
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
    """Cap the agentic loop at ``cap`` code rounds, then force the structured answer.

    Used by the AGENTIC arm only (the static arm uses
    ``StaticOneRoundMiddleware`` + a separate Phase-2 synthesis call). The
    agentic agent is built with ``response_format=ToolStrategy(Answer)``, so the
    factory binds the model with ``tool_choice="any"`` on every turn: the model
    must always pick either ``python_exec`` or the ``Answer`` tool and can never
    emit free-form text (which is where MiniMax used to leak native tool-call
    XML). The arm iterates freely with ``cap=warn_after`` up to the recursion
    guard; the paradigm-specific guidelines block of the system prompt (the
    ``{% if static %}`` branch) carries the other half of the treatment.

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


class StaticOneRoundMiddleware(AgentMiddleware):
    """End the static Phase-1 loop after exactly one ``python_exec`` round.

    The static arm is a two-call pipeline. Phase 1 is a plain CodeAct agent
    (no ``response_format``, no forced ``Answer``, no wrap-up) whose only job is
    to run a single ``python_exec`` round and stop -- the final answer is
    produced separately in Phase 2 (a plain ``init_llm().invoke()`` synthesis,
    see ``run_question``). Once one AI message exists (the ``python_exec`` tool
    call, whose observation is now in state), this middleware short-circuits the
    next model call with an empty ``AIMessage`` that carries no tool calls,
    which ends the agent loop without generating a second tool-calling turn.
    The injected message has no content and no tool calls, so it never enters
    the trace, the steps table, or the token totals.
    """

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
        if ai_count >= 1:
            return ModelResponse(result=[AIMessage(content="")])
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

    if static:
        # Phase 1 of the two-call static pipeline: a plain CodeAct agent that
        # runs exactly one python_exec round and stops. No forced Answer (no
        # response_format -> no tool_choice="any"), no wrap-up injection. The
        # final answer is synthesized separately in run_question (Phase 2).
        agent = create_deep_agent(
            model=llm,
            tools=[python_exec],
            system_prompt=system_prompt,
            middleware=[StaticOneRoundMiddleware()],
        )
    else:
        # Agentic arm: iterate freely up to warn_after, then force a clean
        # structured Answer via the cap turn (tools stripped + wrap-up) and
        # response_format=ToolStrategy(Answer).
        agent = create_deep_agent(
            model=llm,
            tools=[python_exec],
            system_prompt=system_prompt,
            middleware=[CapMiddleware(cap=warn_after)],
            response_format=ToolStrategy(Answer),
        )
    agent._ifc_interpreter = interp
    agent._system_prompt = system_prompt
    # Stashed for run_question: the static flag selects the Phase-2 synthesis
    # branch, and the model id rebuilds the synthesis LLM. Kept on the agent to
    # avoid churning the run_question signature / run_cell.py callsite.
    agent._static = static
    agent._model = model
    agent._max_retries = max_retries
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

    Static arm: Phase 1 runs one ``python_exec`` round (the agent built with
    ``StaticOneRoundMiddleware`` stops after it), then Phase 2 makes a SEPARATE
    plain ``init_llm().invoke()`` synthesis call whose ``.content`` is the final
    answer. Phase-2 tokens and latency are not in ``result["messages"]``, so they
    are summed in explicitly; the synthesis call is not a step and never enters
    the trace.
    """
    if tools:
        # preload() restarts the kernel before seeding the namespace, so the
        # tools arm gets the same clean-kernel-per-question guarantee as the
        # none arm's reset(). This prevents a broken/silent kernel (e.g. left
        # after a timeout) persisting across questions in the tools arm.
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
    trace_entries = _extract_trace(messages)
    in_tok, cached_tok, out_tok, tool_calls = _sum_usage(messages)

    if getattr(agent, "_static", False):
        # Two-call static pipeline: Phase 1 produced the code + observation
        # (above); Phase 2 synthesizes the final answer in a separate plain
        # completion. structured stays None (no Answer tool in this arm).
        structured = None
        answer, synth_elapsed, synth_usage = _synthesize_static_answer(
            agent,
            question=question,
            ifc_path=ifc_path,
            trace_entries=trace_entries,
        )
        elapsed += synth_elapsed
        # Add Phase-2 usage; _sum_usage never saw the synthesis message.
        in_tok += synth_usage[0]
        cached_tok += synth_usage[1]
        out_tok += synth_usage[2]
    else:
        # Agentic arm: the forced structured Answer. The agent loop only ends
        # once the model picks the Answer tool, so this is the user-facing
        # answer.
        structured = result.get("structured_response")
        if isinstance(structured, Answer):
            answer = structured.text.strip()
        else:
            # Defensive guard, not a live path for current providers. With
            # tool_choice="any" the loop ends only by the model picking the
            # Answer tool (which sets structured_response, handled above) or by
            # exceeding recursion_limit, which raises and is recorded as an
            # error row before reaching here. So a returned result with no
            # Answer does not occur today; this falls back to the last AI
            # message carrying text only if some future provider ever returns
            # without calling Answer.
            structured = None
            answer = _normalize_content(messages[-1].content)
            if not answer:
                for msg in reversed(messages):
                    if getattr(msg, "type", None) == "ai":
                        candidate = _normalize_content(msg.content)
                        if candidate:
                            answer = candidate
                            break

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


_THINK_BLOCK_RE = re.compile(r"<\s*think\s*>.*?<\s*/\s*think\s*>", re.DOTALL | re.IGNORECASE)
_FENCE_LINE_RE = re.compile(r"^\s*```[^\n`]*\s*$")


def _strip_synthesis_artifacts(text: str) -> str:
    """Defensively clean the Phase-2 static synthesis completion.

    Phase 2 is a plain (non-tool) completion, so tool-call XML cannot appear,
    but the backbone model may still emit ``<think>...</think>`` reasoning
    blocks or wrap the whole answer in a markdown code fence despite the prompt
    instruction. This strips both post-hoc so the static arm stays clean for any
    backbone, not just MiniMax-M3. Applied ONLY to the static synthesis output;
    the agentic path never calls this.

    1. Remove every ``<think>...</think>`` block (DOTALL, case-insensitive,
       tolerant of whitespace inside the tags).
    2. If the remainder is wrapped in a single markdown code fence (a leading
       line that is ``` optionally followed by a language token, with a matching
       trailing ```), unwrap it to the inner text. Otherwise strip a stray
       leading fence line if present, without removing inner content.
    3. Re-trim whitespace.
    """
    cleaned = _THINK_BLOCK_RE.sub("", text).strip()

    lines = cleaned.split("\n")
    if len(lines) >= 2 and _FENCE_LINE_RE.match(lines[0]):
        # Find a matching trailing fence line (a bare ``` with no language).
        if lines[-1].strip() == "```":
            inner = lines[1:-1]
            # Only unwrap if no fence remains inside the block (single wrapper).
            if not any(line.strip().startswith("```") for line in inner):
                cleaned = "\n".join(inner).strip()
        else:
            # Stray leading fence line without a matching closer: drop just it,
            # but only when it carries no inline content of its own.
            if not any(line.strip().startswith("```") for line in lines[1:]):
                cleaned = "\n".join(lines[1:]).strip()

    return cleaned


def _first_round_code_and_observation(trace_entries: list[dict]) -> tuple[str, str]:
    """Pull the single (code, observation) from a one-round static Phase-1 trace.

    Returns ``("", "")`` when Phase 1 emitted no ``python_exec`` call (model
    error or empty turn), which the caller handles by synthesizing from the
    question alone.
    """
    code = ""
    observation = ""
    for entry in trace_entries:
        if entry.get("role") == "assistant" and not code:
            for tc in entry.get("tool_calls", []):
                code = tc.get("args", {}).get("code", "") or ""
                if code:
                    break
        elif entry.get("role") == "tool" and not observation:
            observation = entry.get("content", "") or ""
    return code, observation


def _synthesize_static_answer(
    agent,
    *,
    question: str,
    ifc_path: str,
    trace_entries: list[dict],
) -> tuple[str, float, tuple[int, int, int]]:
    """Phase 2: synthesize the final static answer in a separate plain completion.

    A plain ``init_llm(...).invoke([...])`` call (no ``response_format``, no
    ``tool_choice``) fed the question, the IFC context, the Phase-1 executed
    code, the Phase-1 kernel observation, and the SAME canonical answer-format
    guidelines the agentic arm uses (extracted from the rendered system prompt).
    The synthesis ``.content`` is the final answer. Because this turn is not a
    tool-calling turn, it cannot leak tool-call markup into the answer.

    Returns ``(answer, elapsed_s, (input_tokens, cached_tokens, output_tokens))``.
    """
    code, observation = _first_round_code_and_observation(trace_entries)
    answer_format = extract_answer_format_section(agent._system_prompt)

    if code:
        evidence = (
            "You ran one `python_exec` inspection of the model. Here is the "
            "exact code you executed and the kernel output it produced.\n\n"
            "Executed code:\n```python\n"
            f"{code}\n```\n\n"
            "Kernel observation:\n```\n"
            f"{observation}\n```"
        )
    else:
        evidence = (
            "No code was executed for this question (the inspection step "
            "produced no output). Answer from the question alone, and if the "
            "information cannot be determined, say so explicitly."
        )

    synth_prompt = (
        "You are a BIM expert. Give the final, user-facing answer to one IFC "
        "question, using ONLY the inspection evidence below.\n\n"
        f"IFC model path: {ifc_path}\n\n"
        f"Question: {question}\n\n"
        f"{evidence}\n\n"
        f"{answer_format}\n\n"
        "Write only the answer prose (and tables if helpful). Do not include "
        "tool-call syntax, code fences, or <think> reasoning blocks."
    )

    synth_llm = init_llm(
        agent._model,
        temperature=0,
        max_retries=getattr(agent, "_max_retries", 3),
    )
    t0 = time.perf_counter()
    synth_msg = synth_llm.invoke([HumanMessage(content=synth_prompt)])
    elapsed = time.perf_counter() - t0

    answer = _strip_synthesis_artifacts(_normalize_content(synth_msg.content))
    usage = getattr(synth_msg, "usage_metadata", None) or {}
    in_tok = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
    out_tok = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0
    cached_tok = 0
    if isinstance(usage, dict):
        details = usage.get("input_token_details") or {}
        if isinstance(details, dict):
            cached_tok = details.get("cache_read", 0) or 0
    return answer, elapsed, (in_tok, cached_tok, out_tok)


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
