"""
Demo script for COBBIE (COde-Based BIM Information Extraction).

Demonstrates functional implementation of BIM question answering
using BAML and CodeAct pattern with MLflow tracing.
"""

import logging
from typing import Callable, Dict

import mlflow
import requests

from src.agents import cobbie
from src.engine.util import get_created_tools
from src.tools.initial import query_ifcopenshell_docs, web_search

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_demo_tools() -> Dict[str, Callable]:
    """Create a comprehensive set of tools for testing COBBIE, including all created tools."""

    # Start with primordial tools
    tools = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "web_search": web_search,
    }

    # Add all created tools from src.tools/created/
    try:
        created_tools = get_created_tools()
        tools.update(created_tools)
        logger.info(f"Loaded {len(created_tools)} created tools")
    except Exception as e:
        logger.warning(f"Could not load created tools: {e}")

    return tools


def demo_basic_functionality():
    """Demonstrate basic COBBIE functionality with metrics."""
    print("🚀 COBBIE Demo: BIM Question Answering with MLflow Tracing")
    print("=" * 60)

    # Set up MLflow experiment for demo
    experiment_name = "COBBIE_Demo"

    # Check if MLflow server is running, otherwise use SQLite
    try:
        # Try to connect to MLflow server first
        requests.get("http://127.0.0.1:5000", timeout=2)
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        print("📊 Connected to MLflow server at http://127.0.0.1:5000")
        print("📊 Traces will be fully visible in the MLflow UI")
    except (requests.RequestException, ImportError):
        # Fallback to SQLite backend
        mlflow.set_tracking_uri("sqlite:///mlflow.sqlite")
        print("📊 Using SQLite MLflow backend (traces will have limited functionality)")
        print(
            "💡 Start MLflow server for full trace viewing: uv run mlflow server --host 127.0.0.1 --port 5000"
        )

    mlflow.set_experiment(experiment_name)
    print(f"📊 MLflow experiment set: {experiment_name}")
    print()

    # Setup
    tools = create_demo_tools()
    question = "How many walls are in the building and what's the building's name?"

    print(f"Question: {question}")
    print(f"Available tools: {list(tools.keys())}")
    print()

    # Execute COBBIE with metrics
    try:
        final_answer, collector, _ = cobbie(
            user_input=question, tools=tools, max_iterations=5
        )

        print("✅ COBBIE Execution Successful!")
        print(f"Answer: {final_answer.answer}")
        print(f"Reasoning: {final_answer.thoughts}")
        print()

        # Display metrics
        if collector and collector.last and collector.last.usage:
            usage = collector.last.usage
            print("📊 Metrics:")
            print(f"  Input tokens: {usage.input_tokens or 0}")
            print(f"  Output tokens: {usage.output_tokens or 0}")
            print(
                f"  Total tokens: {(usage.input_tokens or 0) + (usage.output_tokens or 0)}"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Run COBBIE demonstration."""
    print("COBBIE (COde-Based BIM Information Extraction)")
    print("Functional BAML Implementation with MLflow Tracing")
    print()

    # Run demo directly without additional nested run context
    demo_basic_functionality()

    print("\n" + "=" * 60)
    print("✅ Demo Complete!")
    print()
    print("Key Benefits:")
    print("• Functional paradigm with union types")
    print("• Detailed iteration-level MLflow tracing")
    print("• Comprehensive token usage metrics")
    print("• Backward compatibility with ModuleOutput")
    print()
    print("📊 To view traces:")
    print("• Start MLflow server: uv run mlflow server --host 127.0.0.1 --port 5000")
    print("• Open UI: http://127.0.0.1:5000")
    print("• Navigate to experiment: COBBIE_Demo")


if __name__ == "__main__":
    main()
