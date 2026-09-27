"""SPIKE (throwaway): does enabling MiniMax-M3 extended thinking change outputs?

NOT a production runner. Proves (a) the exact syntax to turn on extended
thinking for ``minimax-anthropic:MiniMax-M3`` over its Anthropic-compatible
endpoint, (b) that it actually engages (thinking content blocks + extra output
tokens), and (c) whether it changes answers / works inside the agentic
ToolStrategy(Answer) loop, on a few benchmark questions.

It writes NOTHING to the real result DBs -- it calls ``run_question`` directly
(which does not persist) and only READS question ids/classifications from
``outputs/factorial/minimax-m3__agentic__none/results.sqlite`` to pick a couple
of previously-wrong and previously-correct questions.

Usage:
    uv run python scripts/spike_thinking.py [--question-ids 1 2 3] [--probe-only]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import time

from src.config import ROOT_PATH
from src.db.load_dataset import TESTSET
from src.harness.agent import create_ifc_agent, run_question
from src.harness.llm import init_llm

MODEL = "minimax-anthropic:MiniMax-M3"
THINKING_ON = {"type": "adaptive"}
BASELINE_DB = os.path.join(
    ROOT_PATH, "outputs", "factorial", "minimax-m3__agentic__none", "results.sqlite"
)


def _pick_questions(n_wrong: int = 2, n_correct: int = 1) -> list[int]:
    """Pick a few qids from the baseline agentic/none run (read-only)."""
    con = sqlite3.connect(f"file:{BASELINE_DB}?mode=ro", uri=True)
    wrong = [
        r[0]
        for r in con.execute(
            "SELECT question_id FROM results WHERE classification='wrong' "
            "ORDER BY question_id LIMIT ?",
            (n_wrong,),
        )
    ]
    correct = [
        r[0]
        for r in con.execute(
            "SELECT question_id FROM results WHERE classification='correct' "
            "ORDER BY question_id LIMIT ?",
            (n_correct,),
        )
    ]
    con.close()
    return wrong + correct


def _qmap() -> dict[int, object]:
    return {q.id: q for q in TESTSET}


def _resolve_ifc(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(ROOT_PATH, path)


def _content_block_types(msg) -> list[str]:
    c = getattr(msg, "content", None)
    if isinstance(c, list):
        return [b.get("type", "?") if isinstance(b, dict) else type(b).__name__ for b in c]
    return ["<str>"]


def _thinking_text_len(msg) -> int:
    c = getattr(msg, "content", None)
    total = 0
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") in ("thinking", "reasoning"):
                total += len(b.get("thinking") or b.get("reasoning") or "")
    return total


def direct_probe() -> None:
    """Low-level proof that the thinking kwarg engages on MiniMax-M3."""
    print("\n" + "=" * 72)
    print("DIRECT PROBE -- raw init_llm().invoke(), reasoning prompt")
    print("=" * 72)
    prompt = (
        "A rectangular wall is 3.5 m long and 2.4 m high and contains two "
        "identical openings of 0.9 m x 2.1 m each. What is the net wall area "
        "in square meters? Give the final number."
    )
    for label, thinking, temp in (("OFF", None, 0), ("ON (adaptive)", THINKING_ON, 1.0)):
        kw = {"thinking": thinking} if thinking else {}
        llm = init_llm(MODEL, temperature=temp, max_tokens=4096, **kw)
        t0 = time.perf_counter()
        try:
            msg = llm.invoke(prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{label}] ERROR: {type(exc).__name__}: {exc}")
            continue
        dt = time.perf_counter() - t0
        usage = getattr(msg, "usage_metadata", None) or {}
        print(f"\n[{label}] temp={temp} thinking={thinking}")
        print(f"  latency={dt:.1f}s  usage={usage}")
        print(f"  content block types: {_content_block_types(msg)}")
        print(f"  thinking text chars: {_thinking_text_len(msg)}")


def harness_probe(qids: list[int]) -> None:
    """Run the real agentic/none cell config per question, thinking OFF vs ON."""
    qmap = _qmap()
    print("\n" + "=" * 72)
    print("HARNESS PROBE -- agentic/none via create_ifc_agent + run_question")
    print("=" * 72)
    for qid in qids:
        q = qmap.get(qid)
        if q is None:
            print(f"\n[q={qid}] not in TESTSET, skipping")
            continue
        ifc_path = _resolve_ifc(q.ifc.model_path)
        print("\n" + "-" * 72)
        print(f"[q={qid}] {q.question[:140]}")
        for label, thinking in (("OFF", None), ("ON", THINKING_ON)):
            agent, interp = create_ifc_agent(
                MODEL, static=False, tools=False, thinking=thinking
            )
            try:
                res = run_question(
                    agent, interp, ifc_path=ifc_path, question=q.question, tools=False
                )
                ans = (res.answer or "").replace("\n", " ")
                print(
                    f"  [{label:>3}] out_tok={res.output_tokens} "
                    f"in_tok={res.input_tokens} tool_calls={res.num_tool_calls} "
                    f"t={res.elapsed_s}s"
                )
                print(f"        answer: {ans[:300]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [{label:>3}] ERROR: {type(exc).__name__}: {exc}")
            finally:
                interp.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question-ids", type=int, nargs="+", default=None)
    ap.add_argument("--probe-only", action="store_true", help="direct probe only")
    args = ap.parse_args()

    direct_probe()
    if args.probe_only:
        return
    qids = args.question_ids or _pick_questions()
    print(f"\nselected question ids: {qids}")
    harness_probe(qids)


if __name__ == "__main__":
    main()
