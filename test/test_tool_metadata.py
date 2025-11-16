"""
Test suite for tool usage stats - Phase 1.1 Tool Metadata Storage
"""

import tempfile
from pathlib import Path
from typing import Generator
import pytest

from sqlmodel import create_engine, SQLModel

# We'll temporarily override ENGINE for testing
import src.db as db_module
from src.db.query import (
    register_new_tool,
    increment_tool_inclusion,
    update_tool_usage,
    get_tool_stats,
    get_all_tool_stats,
    get_last_question_processed,
)


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    # Create a temporary engine
    temp_engine = create_engine(
        f"sqlite:///{temp_db_path}",
        connect_args={"check_same_thread": False}
    )

    # Create all tables
    SQLModel.metadata.create_all(temp_engine)

    # Temporarily override the ENGINE
    original_engine = db_module.ENGINE
    db_module.ENGINE = temp_engine

    yield temp_db_path

    # Restore original ENGINE and cleanup
    db_module.ENGINE = original_engine
    Path(temp_db_path).unlink(missing_ok=True)


def test_table_exists(temp_db: str) -> None:
    """Test that the table is created successfully."""
    # Table should be created by the fixture
    # Just verify we can query it
    stats = get_all_tool_stats()
    assert stats is not None
    assert isinstance(stats, list)


def test_register_new_tool(temp_db: str) -> None:
    """Test registering a new tool."""
    register_new_tool("get_walls", global_question_num=5)

    stats = get_tool_stats("get_walls")
    assert stats is not None
    assert stats.tool_name == "get_walls"
    assert stats.questions_when_included == 0
    assert stats.questions_when_called == 0
    assert stats.questions_correct_contribution == 0
    assert stats.questions_wrong_contribution == 0
    assert stats.created_at_question == 5
    assert stats.last_question_processed == 5


def test_register_multiple_tools(temp_db: str) -> None:
    """Test registering multiple tools at different question numbers."""
    register_new_tool("get_walls", global_question_num=5)
    register_new_tool("get_doors", global_question_num=10)
    register_new_tool("get_windows", global_question_num=15)

    all_stats = get_all_tool_stats()
    assert len(all_stats) == 3

    tool_names = {stat.tool_name for stat in all_stats}
    assert tool_names == {"get_walls", "get_doors", "get_windows"}


def test_increment_tool_inclusion(temp_db: str) -> None:
    """Test incrementing inclusion counters for multiple tools."""
    # Register tools
    register_new_tool("get_walls", global_question_num=0)
    register_new_tool("get_doors", global_question_num=0)

    # Simulate tools being available in questions 1, 2, 3
    for question_num in [1, 2, 3]:
        increment_tool_inclusion(["get_walls", "get_doors"], question_num)

    # Check stats
    walls_stats = get_tool_stats("get_walls")
    assert walls_stats is not None
    assert walls_stats.questions_when_included == 3
    assert walls_stats.last_question_processed == 3

    doors_stats = get_tool_stats("get_doors")
    assert doors_stats is not None
    assert doors_stats.questions_when_included == 3
    assert doors_stats.last_question_processed == 3


def test_update_tool_usage_correct(temp_db: str) -> None:
    """Test updating tool usage when answer is correct."""
    register_new_tool("get_walls", global_question_num=0)

    # Tool was used and answer was correct
    update_tool_usage(["get_walls"], is_correct=True, global_question_num=5)

    stats = get_tool_stats("get_walls")
    assert stats is not None
    assert stats.questions_when_called == 1
    assert stats.questions_correct_contribution == 1
    assert stats.questions_wrong_contribution == 0
    assert stats.last_question_processed == 5


def test_update_tool_usage_wrong(temp_db: str) -> None:
    """Test updating tool usage when answer is wrong."""
    register_new_tool("get_walls", global_question_num=0)

    # Tool was used and answer was wrong
    update_tool_usage(["get_walls"], is_correct=False, global_question_num=5)

    stats = get_tool_stats("get_walls")
    assert stats is not None
    assert stats.questions_when_called == 1
    assert stats.questions_correct_contribution == 0
    assert stats.questions_wrong_contribution == 1


def test_update_tool_usage_multiple_tools(temp_db: str) -> None:
    """Test updating usage for multiple tools used together."""
    register_new_tool("get_walls", global_question_num=0)
    register_new_tool("get_doors", global_question_num=0)

    # Both tools used, answer correct
    update_tool_usage(["get_walls", "get_doors"], is_correct=True, global_question_num=5)

    walls_stats = get_tool_stats("get_walls")
    doors_stats = get_tool_stats("get_doors")

    assert walls_stats is not None
    assert walls_stats.questions_when_called == 1
    assert walls_stats.questions_correct_contribution == 1

    assert doors_stats is not None
    assert doors_stats.questions_when_called == 1
    assert doors_stats.questions_correct_contribution == 1


def test_full_question_lifecycle(temp_db: str) -> None:
    """Test a complete question lifecycle with inclusion and usage tracking."""
    # Question 0: Create tools
    register_new_tool("get_walls", global_question_num=0)
    register_new_tool("get_doors", global_question_num=0)

    # Question 1: Both available, only get_walls used, correct answer
    increment_tool_inclusion(["get_walls", "get_doors"], global_question_num=1)
    update_tool_usage(["get_walls"], is_correct=True, global_question_num=1)

    # Question 2: Both available, both used, wrong answer
    increment_tool_inclusion(["get_walls", "get_doors"], global_question_num=2)
    update_tool_usage(["get_walls", "get_doors"], is_correct=False, global_question_num=2)

    # Question 3: Both available, none used, answer correct (doesn't matter for unused tools)
    increment_tool_inclusion(["get_walls", "get_doors"], global_question_num=3)

    # Verify final stats
    walls_stats = get_tool_stats("get_walls")
    assert walls_stats is not None
    assert walls_stats.questions_when_included == 3
    assert walls_stats.questions_when_called == 2
    assert walls_stats.questions_correct_contribution == 1
    assert walls_stats.questions_wrong_contribution == 1

    doors_stats = get_tool_stats("get_doors")
    assert doors_stats is not None
    assert doors_stats.questions_when_included == 3
    assert doors_stats.questions_when_called == 1
    assert doors_stats.questions_correct_contribution == 0
    assert doors_stats.questions_wrong_contribution == 1


def test_get_last_question_processed(temp_db: str) -> None:
    """Test retrieving the last processed question number."""
    # Initially should return None
    assert get_last_question_processed() is None

    # Register and use tools at different questions
    register_new_tool("tool1", global_question_num=5)
    register_new_tool("tool2", global_question_num=10)

    increment_tool_inclusion(["tool1"], global_question_num=15)
    increment_tool_inclusion(["tool2"], global_question_num=20)

    # Should return the maximum
    assert get_last_question_processed() == 20


def test_get_nonexistent_tool(temp_db: str) -> None:
    """Test retrieving stats for a tool that doesn't exist."""
    stats = get_tool_stats("nonexistent_tool")
    assert stats is None


def test_empty_tool_list_operations(temp_db: str) -> None:
    """Test that operations with empty tool lists don't cause errors."""
    # These should not raise errors
    increment_tool_inclusion([], global_question_num=1)
    update_tool_usage([], is_correct=True, global_question_num=1)


def test_cross_run_scenario(temp_db: str) -> None:
    """Test a scenario simulating multiple training runs with --continue flag."""
    # Run 1: Questions 0-9
    register_new_tool("get_walls", global_question_num=0)
    for q in range(1, 10):
        increment_tool_inclusion(["get_walls"], global_question_num=q)
        if q % 2 == 0:  # Use tool every other question
            update_tool_usage(["get_walls"], is_correct=True, global_question_num=q)

    last_processed = get_last_question_processed()
    assert last_processed == 9

    # Run 2: Questions 10-19 (simulating --continue)
    for q in range(10, 20):
        increment_tool_inclusion(["get_walls"], global_question_num=q)
        if q % 2 == 0:
            update_tool_usage(["get_walls"], is_correct=True, global_question_num=q)

    # Verify continuous tracking
    stats = get_tool_stats("get_walls")
    assert stats is not None
    assert stats.questions_when_included == 19  # Questions 1-19
    assert stats.questions_when_called == 9     # Even questions 2,4,6,8,10,12,14,16,18
    assert stats.questions_correct_contribution == 9
    assert stats.last_question_processed == 19


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
