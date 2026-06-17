"""Smoke test: run one TESTSET question through all four harness combinations.

Exercises the ported CodeAct harness end to end on a single backbone (MiniMax):
kernel exec, observation truncation, static vs agentic, tools vs no-tools, and
token/cached/latency/iteration capture. Not a correctness test -- just proves
the harness runs and reports usable accounting.

Usage:
    uv run python scripts/smoke_harness.py [--model minimax:MiniMax-M2.7] [--qid N]
"""

from __future__ import annotations

import argparse
import os

from src.config import ROOT_PATH
from src.db.load_dataset import TESTSET
from src.harness.agent import create_ifc_agent, run_question


def _resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(ROOT_PATH, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="minimax:MiniMax-M2.7")
    parser.add_argument("--qid", type=int, default=None, help="TESTSET question id")
    parser.add_argument("--recursion-limit", type=int, default=40)
    args = parser.parse_args()

    if args.qid is not None:
        q = next(x for x in TESTSET if x.id == args.qid)
    else:
        q = TESTSET[0]
    ifc_path = _resolve(q.ifc.model_path)

    print(f"model={args.model}")
    print(f"question id={q.id} cat={q.category}")
    print(f"ifc={ifc_path}")
    print(f"Q: {q.question}")
    print(f"GT: {q.ground_truth[:200]}")
    print("=" * 80)

    combos = [
        ("agentic", False, False),
        ("agentic+tools", False, True),
        ("static", True, False),
        ("static+tools", True, True),
    ]

    for label, static, tools in combos:
        print(f"\n### {label} (static={static}, tools={tools})")
        agent, interp = create_ifc_agent(
            args.model, static=static, tools=tools, max_retries=2
        )
        try:
            res = run_question(
                agent,
                interp,
                ifc_path=ifc_path,
                question=q.question,
                tools=tools,
                recursion_limit=args.recursion_limit,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            interp.shutdown()
            continue
        interp.shutdown()

        print(f"  tool_calls={res.num_tool_calls} elapsed={res.elapsed_s}s")
        print(
            f"  tokens in={res.input_tokens} "
            f"cached={res.cached_input_tokens} out={res.output_tokens}"
        )
        print(f"  trace steps={len(res.trace)}")
        ans = res.answer.replace("\n", " ")
        print(f"  answer: {ans[:400]}")


if __name__ == "__main__":
    main()
