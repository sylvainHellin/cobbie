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
            last_question_processed=global_question_num,
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
                tool_stats.last_question_processed = global_question_num
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
                tool_stats.last_question_processed = global_question_num
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


def get_last_question_processed() -> Optional[int]:
    """
    Get the highest last_question_processed value across all tools.
    Useful for resuming training with --continue flag.

    Returns:
        Last processed question number, or None if no tools exist
    """
    with Session(db.ENGINE) as session:
        statement = select(ToolUsageStats).order_by(
            col(ToolUsageStats.last_question_processed).desc()
        ).limit(1)
        result = session.exec(statement).first()
        return result.last_question_processed if result else None
