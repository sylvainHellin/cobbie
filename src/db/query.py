"""
Note: if making any changes in the DB directly, first run:
```zsh
sqlacodegen sqlite:///src/db/db.db --generator sqlmodels --outfile src/db/models.py
```
"""

from functools import wraps
from typing import Callable, List, Optional, TypeVar

from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

import src.db as db
from src.db.models import (
    IfcBench,
    Ifcmodels,
    ToolUsageStats,
    ToolUsageStatsEval,
)

T = TypeVar("T")


def with_session(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that automatically provides a database session as the first argument
    to the decorated function and handles session management.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        with Session(db.ENGINE) as session:
            return func(session, *args, **kwargs)

    return wrapper


def get_dataset(
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    load_ifc_model: bool = False,
) -> List[IfcBench]:
    """
    Return the whole dataset as a List of Dataset

    Args:
        limit: Maximum number of records to return
        offset: Number of records to skip from the beginning
        load_ifc_model: Whether to eager load the IFC model relationship
    """

    with Session(db.ENGINE) as session:
        # base select statement
        statement = select(IfcBench).order_by(col(IfcBench.id).asc())

        # offset if provided
        if offset:
            statement = statement.offset(offset)

        # limit if limit provided
        if limit:
            statement = statement.limit(limit)

        # Eager loading of the relationship
        if load_ifc_model:
            statement = statement.options(selectinload(getattr(IfcBench, "ifc")))

        dataset = [row for row in session.exec(statement)]
        return dataset


def get_ifc_model(id: int) -> Optional[Ifcmodels]:
    """
    Get the IFC Model from the database from it's id, or None if non is found.
    """
    with Session(db.ENGINE) as session:
        ifc_model = session.get(Ifcmodels, id)
        return ifc_model


def get_ifc_models() -> List[Ifcmodels]:
    """
    Retrieve all IFC models from the Database
    """
    with Session(db.ENGINE) as session:
        results = session.exec(select(Ifcmodels))
        ifc_models = [model for model in results]
        return ifc_models


# Tool Usage Stats Functions

def register_new_tool(name: str, global_question_num: int) -> None:
    """
    Initialize a metadata entry for a newly created tool.

    Args:
        name: Tool name (without .py extension)
        global_question_num: Global question number when tool was created
    """
    with Session(db.ENGINE) as session:
        tool_stats = ToolUsageStats(
            tool_name=name,
            questions_when_included=0,
            questions_when_called=0,
            questions_correct_contribution=0,
            questions_wrong_contribution=0,
            created_at_question=global_question_num,
        )
        session.merge(tool_stats)  # Use merge to handle INSERT OR REPLACE
        session.commit()


def increment_tool_inclusion(tool_names: List[str], global_question_num: int) -> None:
    """
    Increment the inclusion counter for all tools that were available in this question.

    Args:
        tool_names: List of tool names that were in the available toolbox
        global_question_num: Current global question number
    """
    if not tool_names:
        return

    with Session(db.ENGINE) as session:
        for tool_name in tool_names:
            tool_stats = session.get(ToolUsageStats, tool_name)
            if tool_stats:
                tool_stats.questions_when_included = (tool_stats.questions_when_included or 0) + 1
                session.add(tool_stats)
        session.commit()


def update_tool_usage(
    tool_names: List[str],
    is_correct: bool,
    global_question_num: int
) -> None:
    """
    Update usage statistics for tools that were actually called in this question.

    Args:
        tool_names: List of tool names that were invoked during execution
        is_correct: Whether the final answer was correct
        global_question_num: Current global question number
    """
    if not tool_names:
        return

    with Session(db.ENGINE) as session:
        for tool_name in tool_names:
            tool_stats = session.get(ToolUsageStats, tool_name)
            if tool_stats:
                tool_stats.questions_when_called = (tool_stats.questions_when_called or 0) + 1
                if is_correct:
                    tool_stats.questions_correct_contribution = (
                        tool_stats.questions_correct_contribution or 0
                    ) + 1
                else:
                    tool_stats.questions_wrong_contribution = (
                        tool_stats.questions_wrong_contribution or 0
                    ) + 1
                session.add(tool_stats)
        session.commit()


def get_tool_stats(tool_name: str) -> Optional[ToolUsageStats]:
    """
    Retrieve statistics for a single tool.

    Args:
        tool_name: Name of the tool

    Returns:
        ToolUsageStats object, or None if tool not found
    """
    with Session(db.ENGINE) as session:
        tool_stats = session.get(ToolUsageStats, tool_name)
        if tool_stats:
            # Refresh to ensure all attributes are loaded before session closes
            session.refresh(tool_stats)
        return tool_stats


def get_all_tool_stats() -> List[ToolUsageStats]:
    """
    Retrieve statistics for all tools.

    Returns:
        List of ToolUsageStats objects
    """
    with Session(db.ENGINE) as session:
        statement = select(ToolUsageStats).order_by(col(ToolUsageStats.tool_name).asc())
        results = session.exec(statement)
        return [stat for stat in results]


def calculate_deletion_score(
    tool_stats: ToolUsageStats,
    grace_period: int = 16
) -> float:
    """
    Calculate deletion score (0-100, higher = more deletable).

    Formula combines:
    - Call rate (how often used when available)
    - Success rate (contribution to correct answers)
    - Failure penalty (contribution to wrong answers)

    Returns:
        0.0 if within grace period (fewer inclusions than grace_period)
        100.0 if never called after grace period
        <20.0 for high-value tools
        >70.0 for harmful tools
    """
    included = tool_stats.questions_when_included or 0
    called = tool_stats.questions_when_called or 0
    correct = tool_stats.questions_correct_contribution or 0
    wrong = tool_stats.questions_wrong_contribution or 0

    # Grace period protection - protect tools that haven't had enough opportunities
    if included < grace_period:
        return 0.0

    # Never called after grace period = high deletion score
    if called == 0:
        return (100.0 - 1/included)

    # Calculate rates
    call_rate = called / included
    success_rate = correct / called if called > 0 else 0.0
    failure_rate = wrong / called if called > 0 else 0.0

    # Weighted score (0-100)
    # Increased weight on call_rate since we removed age_score
    call_score = (1.0 - call_rate) * 50
    success_score = (1.0 - success_rate) * 25
    failure_score = failure_rate * 25

    return min(call_score + success_score + failure_score, 100.0)


def get_tools_ranked_by_deletion_score(
    grace_period: int = 16
) -> List[tuple[str, float]]:
    """
    Get all tools ranked by deletion score (highest first).

    Args:
        grace_period: Number of inclusions to protect new tools from deletion

    Returns:
        List of (tool_name, score) tuples, sorted descending
    """
    all_stats = get_all_tool_stats()

    scored_tools: List[tuple[str, float]] = [
        (stats.tool_name, calculate_deletion_score(stats, grace_period))
        for stats in all_stats
        if stats.tool_name is not None
    ]

    scored_tools.sort(key=lambda x: x[1], reverse=True)
    return scored_tools


def calculate_deletion_score_exponential(
    tool_stats: ToolUsageStats,
    grace_period: int = 8,
    alpha: float = 2.0,
    beta: float = 2.0,
) -> float:
    """
    Calculate deletion score using exponential formula (higher = more deletable).

    Formula: score = exp(exp(-α × call_rate) + exp(-β × success_rate))

    Where:
    - call_rate: called / included (how often used when available, 0-1)
    - success_rate: correct / called (success when used, 0-1)
    - α: controls sensitivity to usage rate (higher α = more penalty for low usage)
    - β: controls sensitivity to success rate (higher β = more penalty for low success)

    Note: failure_rate is redundant since failure_rate = 1 - success_rate
    (correct + wrong always equals called in our tracking system)

    Returns:
        0.0 if within grace period (fewer inclusions than grace_period)
        deletion score otherwise (lower is better)
    """
    import math

    included = tool_stats.questions_when_included or 0
    called = tool_stats.questions_when_called or 0
    correct = tool_stats.questions_correct_contribution or 0

    # Grace period protection
    if included < grace_period:
        return 0.0

    # Calculate rates
    call_rate = called / included
    success_rate = correct / called if called > 0 else 0.0

    # Exponential terms
    # - exp(-α × call_rate): high (→1) when call_rate is low (→0), low (→0) when call_rate is high (→1)
    # - exp(-β × success_rate): high (→1) when success_rate is low (→0), low (→0) when success_rate is high (→1)
    usage_term = math.exp(-alpha * call_rate)
    success_term = math.exp(-beta * success_rate)

    # Combined score
    # Two terms sum to range [0, 2] approximately
    raw_score = usage_term + success_term
    final_score = math.exp(raw_score)

    return final_score


def delete_tool_from_db(tool_name: str) -> None:
    """Delete tool metadata from database."""
    with Session(db.ENGINE) as session:
        tool_stats = session.get(ToolUsageStats, tool_name)
        if tool_stats:
            session.delete(tool_stats)
            session.commit()


def initialize_tool_metadata(global_question_num: int) -> int:
    """
    Initialize metadata for existing tools without entries.

    Returns:
        Number of tools initialized
    """
    from src.util import get_created_tools

    existing_tools = get_created_tools()
    initialized_count = 0

    with Session(db.ENGINE) as session:
        for tool_name in existing_tools.keys():
            existing_stats = session.get(ToolUsageStats, tool_name)
            if not existing_stats:
                tool_stats = ToolUsageStats(
                    tool_name=tool_name,
                    questions_when_included=0,
                    questions_when_called=0,
                    questions_correct_contribution=0,
                    questions_wrong_contribution=0,
                    created_at_question=global_question_num,
                )
                session.add(tool_stats)
                initialized_count += 1

        session.commit()

    return initialized_count


# Evaluation Tool Usage Stats Functions

def increment_eval_tool_inclusion(tool_names: List[str]) -> None:
    """
    Increment the inclusion counter for all tools available in this evaluation question.

    Args:
        tool_names: List of tool names that were in the available toolbox
    """
    if not tool_names:
        return

    with Session(db.ENGINE) as session:
        for tool_name in tool_names:
            tool_stats = session.get(ToolUsageStatsEval, tool_name)
            if tool_stats:
                tool_stats.questions_when_included = (tool_stats.questions_when_included or 0) + 1
                session.add(tool_stats)
            else:
                # Create new entry if tool doesn't exist
                tool_stats = ToolUsageStatsEval(
                    tool_name=tool_name,
                    questions_when_included=1,
                    questions_when_called=0,
                    questions_correct_contribution=0,
                    questions_wrong_contribution=0,
                )
                session.add(tool_stats)
        session.commit()


def update_eval_tool_usage(tool_names: List[str], is_correct: bool) -> None:
    """
    Update usage statistics for tools that were actually called in this evaluation question.

    Args:
        tool_names: List of tool names that were invoked during execution
        is_correct: Whether the final answer was correct
    """
    if not tool_names:
        return

    with Session(db.ENGINE) as session:
        for tool_name in tool_names:
            tool_stats = session.get(ToolUsageStatsEval, tool_name)
            if tool_stats:
                tool_stats.questions_when_called = (tool_stats.questions_when_called or 0) + 1
                if is_correct:
                    tool_stats.questions_correct_contribution = (
                        tool_stats.questions_correct_contribution or 0
                    ) + 1
                else:
                    tool_stats.questions_wrong_contribution = (
                        tool_stats.questions_wrong_contribution or 0
                    ) + 1
                session.add(tool_stats)
        session.commit()


def get_all_eval_tool_stats() -> List[ToolUsageStatsEval]:
    """
    Retrieve statistics for all evaluation tools.

    Returns:
        List of ToolUsageStatsEval objects, ordered by tool name
    """
    with Session(db.ENGINE) as session:
        statement = select(ToolUsageStatsEval).order_by(col(ToolUsageStatsEval.tool_name).asc())
        results = session.exec(statement)
        return [stat for stat in results]


def clear_eval_tool_stats() -> int:
    """
    Clear all evaluation tool statistics.

    Returns:
        Number of rows deleted
    """
    with Session(db.ENGINE) as session:
        statement = select(ToolUsageStatsEval)
        results = session.exec(statement)
        stats_to_delete = [stat for stat in results]

        count = len(stats_to_delete)
        for stat in stats_to_delete:
            session.delete(stat)

        session.commit()
        return count
