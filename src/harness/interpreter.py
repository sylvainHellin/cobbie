"""Persistent Python interpreter backed by a Jupyter kernel.

Ported from the sibling ``bim-query-comparison/pipelines/ifc/interpreter.py``.
The kernel persists variables/imports across ``python_exec`` calls within a
single question; ``reset()`` restarts it between questions so accumulated state
never leaks across the factorial (the old custom interpreter was the leak
source).

The tools axis preloads curated helpers into the kernel namespace via
``preload(namespace_setup_code)``: CodeAct stays pure (the agent's only action
is writing Python), and the helpers are ordinary callables in scope, not
separate LangChain tools.
"""

from __future__ import annotations

import re
import time

import jupyter_client
import tiktoken

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Token budget for a single `python_exec` output. 8192 cl100k_base tokens is
# ~32kB of plain text: large enough to show structure or a traceback, small
# enough that one verbose call cannot dominate the model context window even
# after 15-20 tool calls.
_DEFAULT_MAX_OUTPUT_TOKENS = 8192

# Split the budget 70/30 head/tail so the agent sees both the start (schema,
# first entities) and end (summary counts, final error lines) of long output.
_HEAD_FRACTION = 0.70

# Module-level encoder -- `get_encoding` has a small first-call I/O cost.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def _truncate_by_tokens(text: str, budget: int) -> str:
    """Truncate ``text`` to at most ``budget`` tokens, keeping a head+tail slice."""
    ids = _ENCODING.encode(text)
    total = len(ids)
    if total <= budget:
        return text

    head_n = max(1, int(budget * _HEAD_FRACTION))
    tail_n = max(1, budget - head_n)
    dropped = total - head_n - tail_n

    head = _ENCODING.decode(ids[:head_n])
    tail = _ENCODING.decode(ids[-tail_n:])

    marker = (
        f"\n\n... [OUTPUT TRUNCATED. {dropped} of {total} tokens omitted "
        f"(budget: {budget} tokens). The previous tool call produced too much "
        f"text -- narrow your next query: slice the list, aggregate before "
        f"printing, or print only the fields you need.] ...\n\n"
    )
    return head + marker + tail


class JupyterInterpreter:
    """Persistent Python interpreter backed by a Jupyter kernel."""

    def __init__(self, max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS) -> None:
        self.max_output_tokens = max_output_tokens
        self._preamble: str = ""
        self.km = jupyter_client.KernelManager()
        self.km.start_kernel()
        self.kc = self.km.blocking_client()
        self.kc.wait_for_ready(timeout=30)

    # ------------------------------------------------------------------
    # Namespace preloading (tools axis)
    # ------------------------------------------------------------------

    def preload(self, setup_code: str) -> str:
        """Execute *setup_code* to seed the kernel namespace and remember it.

        Used by the tools arm to inject the curated helper library and any
        common imports. The code is re-run after every ``reset()`` so each
        question starts from the same preloaded namespace. Returns the raw
        execution output (empty on success); raises nothing.
        """
        self._preamble = setup_code
        return self.run(setup_code)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, code: str, timeout: int = 60) -> str:
        """Execute *code* in the kernel and return collected output."""
        msg_id = self.kc.execute(code)
        output_parts: list[str] = []
        deadline = time.monotonic() + timeout

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError

                try:
                    iopub_msg = self.kc.get_iopub_msg(timeout=remaining)
                except Exception:
                    # Channel closed or kernel died.
                    break

                if iopub_msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue

                msg_type = iopub_msg["header"]["msg_type"]
                content = iopub_msg["content"]

                if msg_type == "stream":
                    output_parts.append(content.get("text", ""))
                elif msg_type == "execute_result":
                    data = content.get("data", {})
                    output_parts.append(data.get("text/plain", ""))
                elif msg_type == "error":
                    tb = "\n".join(content.get("traceback", []))
                    output_parts.append(_ANSI_RE.sub("", tb))
                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break

        except TimeoutError:
            self.interrupt()
            return f"[Timeout] Execution exceeded {timeout}s and was interrupted."

        result = "".join(output_parts)
        return _truncate_by_tokens(result, self.max_output_tokens)

    # ------------------------------------------------------------------
    # Kernel lifecycle helpers
    # ------------------------------------------------------------------

    def interrupt(self) -> None:
        """Send SIGINT to the kernel."""
        try:
            self.km.interrupt_kernel()
        except Exception:
            pass

    def reset(self) -> None:
        """Restart the kernel with a clean namespace, re-applying any preamble."""
        self.km.restart_kernel(now=True)
        self.kc.wait_for_ready(timeout=30)
        if self._preamble:
            self.run(self._preamble)

    def shutdown(self) -> None:
        """Shut down the kernel immediately."""
        try:
            self.km.shutdown_kernel(now=True)
        except Exception:
            pass

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass
