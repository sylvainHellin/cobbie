"""
Display statistics for all tools in the database.

Usage:
    uv run scripts/display_tool_stats.py              # Show only existing tools (default)
    uv run scripts/display_tool_stats.py --all        # Show all tools (including deleted)
"""

import argparse
from typing import List

from tabulate import tabulate

from src.db.models import ToolUsageStats
from src.db.query import get_all_tool_stats
from src.util.get_created_tools import get_created_tools


def display_tool_stats(show_all: bool = False) -> None:
    """
    Display statistics for all tools.

    Args:
        show_all: If True, display stats for all tools in the database (including deleted).
                  If False, only display stats for tools that currently exist in the filesystem.
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

    # Prepare table data
    table_data = []
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

        # Mark deleted tools
        status = "🗑️" if tool_name not in existing_tool_names else ""

        table_data.append([
            f"{tool_name}{' ' + status if status else ''}",
            created_at,
            included,
            called,
            f"{call_rate:.1f}%" if included > 0 else "N/A",
            correct,
            wrong,
            f"{success_rate:.1f}%" if called > 0 else "N/A"
        ])

    # Print table
    print("\n🔧 Tool Statistics:")
    headers = ["Tool Name", "Created", "Included", "Called", "Call Rate", "Correct", "Wrong", "Success Rate"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

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
  uv run scripts/display_tool_stats.py              # Show only existing tools (default)
  uv run scripts/display_tool_stats.py --all        # Show all tools (including deleted)
        """
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Display all tools including deleted ones (default: show only existing tools)"
    )

    args = parser.parse_args()
    display_tool_stats(show_all=args.all)


if __name__ == "__main__":
    main()
