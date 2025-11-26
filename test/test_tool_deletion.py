"""Test tool deletion scoring."""

from src.db.models import ToolUsageStats
from src.db.query import calculate_deletion_score


def test_grace_period_protection():
    """New tools should have score 0."""
    stats = ToolUsageStats(
        tool_name="new_tool",
        created_at_question=100,
        questions_when_included=10,
        questions_when_called=5,
        questions_correct_contribution=5,
        questions_wrong_contribution=0,
    )

    score = calculate_deletion_score(stats, current_question_num=115, grace_period=25)
    assert score == 0.0


def test_never_used_tool():
    """Never-used tools should have max score."""
    stats = ToolUsageStats(
        tool_name="unused",
        created_at_question=50,
        questions_when_included=0,
        questions_when_called=0,
        questions_correct_contribution=0,
        questions_wrong_contribution=0,
    )

    score = calculate_deletion_score(stats, current_question_num=200, grace_period=25)
    assert score == 100.0


def test_high_value_tool():
    """High-usage tools should have low score."""
    stats = ToolUsageStats(
        tool_name="valuable",
        created_at_question=150,  # Younger tool (age = 50)
        questions_when_included=40,
        questions_when_called=38,
        questions_correct_contribution=37,
        questions_wrong_contribution=1,
    )

    score = calculate_deletion_score(stats, current_question_num=200, grace_period=25)
    # Very high call rate (38/40 = 95%), very high success rate (37/38 = 97.4%)
    # Score should be low (less than 20)
    assert score < 20.0


def test_low_usage_tool():
    """Tools with low usage should have higher score."""
    stats = ToolUsageStats(
        tool_name="rarely_used",
        created_at_question=50,
        questions_when_included=100,
        questions_when_called=5,
        questions_correct_contribution=2,
        questions_wrong_contribution=3,
    )

    score = calculate_deletion_score(stats, current_question_num=200, grace_period=25)
    assert score > 50.0


def test_harmful_tool():
    """Tools that contribute to wrong answers should have high score."""
    stats = ToolUsageStats(
        tool_name="harmful",
        created_at_question=50,
        questions_when_included=100,
        questions_when_called=50,
        questions_correct_contribution=5,
        questions_wrong_contribution=45,
    )

    score = calculate_deletion_score(stats, current_question_num=200, grace_period=25)
    assert score > 70.0


def test_tool_at_grace_period_boundary():
    """Tool exactly at grace period boundary should be protected."""
    stats = ToolUsageStats(
        tool_name="boundary_tool",
        created_at_question=175,
        questions_when_included=10,
        questions_when_called=5,
        questions_correct_contribution=5,
        questions_wrong_contribution=0,
    )

    # At boundary (age = 24, grace_period = 25)
    score = calculate_deletion_score(stats, current_question_num=199, grace_period=25)
    assert score == 0.0

    # Just past boundary (age = 25, grace_period = 25)
    score = calculate_deletion_score(stats, current_question_num=200, grace_period=25)
    assert score > 0.0
