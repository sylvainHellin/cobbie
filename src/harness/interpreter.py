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
from queue import Empty

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
        """Restart the kernel, then execute *setup_code* to seed the namespace.

        Used by the tools arm to inject the curated helper library and any
        common imports. Restarting first makes per-question kernel handling
        symmetric with the none arm's ``reset()``: a kernel left in a broken
        state (e.g. post-timeout) by the previous question can never persist
        into this one. The code is also re-run after every ``reset()`` so each
        question starts from the same preloaded namespace. Returns the raw
        execution output (empty on success); raises nothing.
        """
        self._preamble = setup_code
        self._restart()
        return self.run(setup_code)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, code: str, timeout: int = 60) -> str:
        """Execute *code* in the kernel and return collected output.

        On timeout the runaway cell is interrupted (SIGINT) and any stale iopub
        messages it left behind are drained, so the *next* execute is not
        poisoned by output attributed to an already-returned request. This is
        the fix for the silent-stdout blackout: previously a deadline made
        ``get_iopub_msg`` raise ``queue.Empty``, which the broad ``except`` swallowed
        with a bare ``break`` -- no interrupt, no marker, and the runaway cell's
        late output then leaked onto subsequent executes and was dropped by the
        ``parent_header`` filter, blacking out stdout for the rest of the question.
        """
        msg_id = self.kc.execute(code)
        output_parts: list[str] = []
        deadline = time.monotonic() + timeout
        timed_out = False

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break

            try:
                iopub_msg = self.kc.get_iopub_msg(timeout=remaining)
            except Empty:
                # No message before the deadline: the cell is still running.
                timed_out = True
                break
            except Exception:
                # Channel closed or kernel died -- nothing more to collect.
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

        if timed_out:
            self._recover_from_timeout()
            return f"[Timeout] Execution exceeded {timeout}s and was interrupted."

        result = "".join(output_parts)
        return _truncate_by_tokens(result, self.max_output_tokens)

    def _recover_from_timeout(self) -> None:
        """Interrupt a runaway cell and drain its stale output.

        SIGINT stops the cell, then we wait for the kernel to return to ``idle``
        and flush every queued iopub/shell message left over from the killed
        execute. Without this drain, the dead cell's late ``stream``/``status``
        messages sit in the channel and get mis-attributed -- the next execute
        sees the leftover ``idle`` and returns before its own output arrives,
        which is the first-print-after-timeout blackout. If the kernel will not
        come back to a clean idle state, fall back to a full restart so the next
        question always starts from a working kernel.
        """
        self.interrupt()
        drained_to_idle = False
        drain_deadline = time.monotonic() + 10
        while time.monotonic() < drain_deadline:
            try:
                msg = self.kc.get_iopub_msg(timeout=1)
            except Empty:
                # Channel quiet; if we already saw idle we are clean.
                if drained_to_idle:
                    break
                continue
            except Exception:
                break
            content = msg.get("content", {})
            if (
                msg.get("header", {}).get("msg_type") == "status"
                and content.get("execution_state") == "idle"
            ):
                drained_to_idle = True
        # Flush any pending shell replies (e.g. the interrupted execute_reply)
        # so they cannot be mismatched against the next execute.
        while True:
            try:
                self.kc.get_shell_msg(timeout=0.2)
            except Empty:
                break
            except Exception:
                break
        if not drained_to_idle:
            # Interrupt did not cleanly settle the kernel; restart it so the
            # next execute is guaranteed to deliver its output.
            self.reset()

    # ------------------------------------------------------------------
    # Kernel lifecycle helpers
    # ------------------------------------------------------------------

    def interrupt(self) -> None:
        """Send SIGINT to the kernel."""
        try:
            self.km.interrupt_kernel()
        except Exception:
            pass

    def _restart(self) -> None:
        """Restart the kernel process and wait for it to be ready."""
        self.km.restart_kernel(now=True)
        self.kc.wait_for_ready(timeout=30)

    def reset(self) -> None:
        """Restart the kernel with a clean namespace, re-applying any preamble."""
        self._restart()
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
