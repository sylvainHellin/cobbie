"""Prune created tools down to a target count based on deletion scores."""

import argparse

from src.db.query import (
    calculate_deletion_score,
    calculate_deletion_score_exponential,
    get_all_tool_stats,
)
from src.util.delete_tool import delete_tool


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune created tools by deletion score")
    parser.add_argument("--target", type=int, default=24, help="Number of tools to keep (default: 24)")
    parser.add_argument("--grace-period", type=int, default=0, help="Grace period for scoring (default: 0)")
    parser.add_argument("--scoring", choices=["linear", "exponential"], default="linear", help="Scoring method")
    parser.add_argument("--alpha", type=float, default=2.0, help="Alpha param for exponential scoring")
    parser.add_argument("--beta", type=float, default=2.0, help="Beta param for exponential scoring")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    all_stats = get_all_tool_stats()
    if not all_stats:
        print("No tool stats found in database.")
        return

    # Compute scores
    scored: list[tuple[str, float]] = []
    for stats in all_stats:
        if stats.tool_name is None:
            continue
        if args.scoring == "exponential":
            score = calculate_deletion_score_exponential(
                stats, grace_period=args.grace_period, alpha=args.alpha, beta=args.beta
            )
        else:
            score = calculate_deletion_score(stats, grace_period=args.grace_period)
        scored.append((stats.tool_name, score))

    # Sort by score descending (highest = most deletable)
    scored.sort(key=lambda x: x[1], reverse=True)

    total = len(scored)
    n_to_delete = max(0, total - args.target)

    if n_to_delete == 0:
        print(f"Currently {total} tools, target is {args.target}. Nothing to prune.")
        return

    to_delete = set(name for name, _ in scored[:n_to_delete])

    # Display table
    print(f"\n{'Tool':<50} {'Score':>10}   Fate")
    print("-" * 75)
    for name, score in scored:
        fate = "DELETE" if name in to_delete else "keep"
        print(f"{name:<50} {score:>10.2f}   {fate}")

    print(f"\nTotal: {total} | Keep: {total - n_to_delete} | Delete: {n_to_delete}")

    if args.dry_run:
        print("\n[dry-run] No tools were deleted.")
        return

    # Confirmation
    if not args.yes:
        answer = input(f"\nDelete {n_to_delete} tools? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    # Delete
    deleted = 0
    failed = 0
    for name in to_delete:
        if delete_tool(name):
            deleted += 1
            print(f"  Deleted: {name}")
        else:
            failed += 1
            print(f"  FAILED:  {name}")

    print(f"\nDone. Deleted {deleted} tools, {failed} failures.")


if __name__ == "__main__":
    main()
