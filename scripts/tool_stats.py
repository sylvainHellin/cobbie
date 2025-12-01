"""
Display statistics for all tools in the database.

Usage:
    uv run scripts/tool_stats.py                              # Show only existing tools (default)
    uv run scripts/tool_stats.py --all                        # Show all tools (including deleted)
    uv run scripts/tool_stats.py --sort-by called             # Sort by number of times called
    uv run scripts/tool_stats.py --sort-by success-rate       # Sort by success rate (descending)
    uv run scripts/tool_stats.py --sort-by deletion-score     # Sort by deletion score (descending)
    uv run scripts/tool_stats.py --grace-period 30            # Use grace period of 30 inclusions
"""

import argparse
from typing import Any, List, Tuple

from tabulate import tabulate

from src.db.models import ToolUsageStats
from src.db.query import calculate_deletion_score, get_all_tool_stats
from src.util.get_created_tools import get_created_tools


def display_tool_stats(show_all: bool = False, sort_by: str = "name", grace_period: int = 25) -> None:
    """
    Display statistics for all tools.

    Args:
        show_all: If True, display stats for all tools in the database (including deleted).
                  If False, only display stats for tools that currently exist in the filesystem.
        sort_by: Column to sort by. Options: name, created, included, called, call-rate, correct, wrong, success-rate, deletion-score
        grace_period: Number of inclusions to protect new tools from deletion (default: 25)
    """
    # Get all tool stats from database
    all_stats: List[ToolUsageStats] = get_all_tool_stats()
    total_in_db = len(all_stats)

    # Get existing tools to filter and identify deleted ones
    existing_tools = get_created_tools()
    existing_tool_names = set(existing_tools.keys())

    # Filter stats based on show_all flag
    if not show_all:
        all_stats = [stat for stat in all_stats if stat.tool_name in existing_tool_names]

    if not all_stats:
        print(f"\n{'No tools found in database.' if show_all else 'No existing tools found.'}\n")
        return

    deleted_count = total_in_db - len(existing_tool_names)

    # Print header
    print("\n" + "=" * 80)
    print("TOOL USAGE STATISTICS")
    print("=" * 80)

    # Print summary counts
    print("\n📊 Overview:")
    print(f"  Existing tools: {len(existing_tool_names)}")
    print(f"  Deleted tools: {deleted_count}")
    print(f"  Displaying: {len(all_stats)} tool(s) {'(all tools)' if show_all else '(existing only)'}")
    print(f"  Sorted by: {sort_by}")
    print(f"  Grace period: {grace_period} inclusions")

    # Prepare table data with sorting
    table_data: List[Tuple[Any, ...]] = []
    for stat in all_stats:
        tool_name = stat.tool_name or "Unknown"
        created_at = stat.created_at_question or 0
        included = stat.questions_when_included or 0
        called = stat.questions_when_called or 0
        correct = stat.questions_correct_contribution or 0
        wrong = stat.questions_wrong_contribution or 0

        # Calculate derived metrics
        call_rate = (called / included * 100) if included > 0 else 0
        success_rate = (correct / called * 100) if called > 0 else 0
        deletion_score = calculate_deletion_score(stat, grace_period)

        # Mark deleted tools
        status = "🗑️" if tool_name not in existing_tool_names else ""

        table_data.append((
            f"{tool_name}{' ' + status if status else ''}",
            created_at,
            included,
            called,
            call_rate,
            correct,
            wrong,
            success_rate,
            deletion_score,
            # Store raw values for sorting
            tool_name,
        ))

    # Sort the data
    sort_key_map = {
        "name": lambda x: x[9].lower(),  # Sort by raw tool name (case-insensitive)
        "created": lambda x: x[1],
        "included": lambda x: x[2],
        "called": lambda x: x[3],
        "call-rate": lambda x: x[4],
        "correct": lambda x: x[5],
        "wrong": lambda x: x[6],
        "success-rate": lambda x: x[7],
        "deletion-score": lambda x: x[8],
    }

    # Determine sort order (descending for most metrics, ascending for name)
    reverse = sort_by != "name"

    if sort_by in sort_key_map:
        table_data.sort(key=sort_key_map[sort_by], reverse=reverse)

    # Format table data for display
    formatted_table = []
    for row in table_data:
        formatted_table.append([
            row[0],  # Tool name with status
            row[1],  # Created
            row[2],  # Included
            row[3],  # Called
            f"{row[4]:.1f}%" if row[2] > 0 else "N/A",  # Call rate
            row[5],  # Correct
            row[6],  # Wrong
            f"{row[7]:.1f}%" if row[3] > 0 else "N/A",  # Success rate
            f"{row[8]:.1f}" if row[2] >= grace_period else "Protected",  # Deletion score
        ])

    # Print table
    print("\n🔧 Tool Statistics:")
    headers = ["Tool Name", "Created", "Included", "Called", "Call Rate", "Correct", "Wrong", "Success Rate", "Del Score"]
    print(tabulate(formatted_table, headers=headers, tablefmt="grid"))

    # Calculate and print summary statistics
    total_included = sum(stat.questions_when_included or 0 for stat in all_stats)
    total_called = sum(stat.questions_when_called or 0 for stat in all_stats)
    total_correct = sum(stat.questions_correct_contribution or 0 for stat in all_stats)
    total_wrong = sum(stat.questions_wrong_contribution or 0 for stat in all_stats)

    print("\n📈 Summary Statistics:")
    summary_data = [
        ["Total Inclusions", f"{total_included:,}"],
        ["Total Calls", f"{total_called:,}"],
        ["Total Correct Contributions", f"{total_correct:,}"],
        ["Total Wrong Contributions", f"{total_wrong:,}"],
    ]

    if total_called > 0:
        overall_call_rate = (total_called / total_included * 100) if total_included > 0 else 0
        overall_success_rate = (total_correct / total_called * 100)
        summary_data.append(["Overall Call Rate", f"{overall_call_rate:.1f}%"])
        summary_data.append(["Overall Success Rate", f"{overall_success_rate:.1f}%"])

    print(tabulate(summary_data, tablefmt="simple"))
    print("\n" + "=" * 80 + "\n")


def main() -> None:
    """Parse arguments and display tool statistics."""
    parser = argparse.ArgumentParser(
        description="Display statistics for tools in the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run scripts/tool_stats.py                              # Show only existing tools (default)
  uv run scripts/tool_stats.py --all                        # Show all tools (including deleted)
  uv run scripts/tool_stats.py --sort-by called             # Sort by number of times called
  uv run scripts/tool_stats.py --sort-by success-rate       # Sort by success rate (descending)
  uv run scripts/tool_stats.py --sort-by deletion-score     # Sort by deletion score (descending)
  uv run scripts/tool_stats.py --grace-period 30            # Use grace period of 30 inclusions
  uv run scripts/tool_stats.py --all --sort-by call-rate    # Combine filters and sorting
        """
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Display all tools including deleted ones (default: show only existing tools)"
    )

    parser.add_argument(
        "--sort-by",
        choices=["name", "created", "included", "called", "call-rate", "correct", "wrong", "success-rate", "deletion-score"],
        default="name",
        help="Column to sort by (default: name). Most columns sort descending except 'name' which sorts ascending."
    )

    parser.add_argument(
        "--grace-period",
        type=int,
        default=25,
        help="Number of inclusions to protect new tools from deletion (default: 25)"
    )

    args = parser.parse_args()
    display_tool_stats(show_all=args.all, sort_by=args.sort_by, grace_period=args.grace_period)


if __name__ == "__main__":
    main()
