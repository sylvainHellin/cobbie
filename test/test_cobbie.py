"""
Demo script for COBBIE (COde-Based BIM Information Extraction).

Demonstrates functional implementation of BIM question answering
using BAML and CodeAct pattern with MLflow tracing.
"""

import logging
import mlflow
from typing import Dict, Callable

from src.engine.components.cobbie import cobbie, cobbie_with_metrics
from src.engine.tools.primordial import query_ifcopenshell_docs, web_search

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_demo_tools() -> Dict[str, Callable]:
    """Create a set of demo tools for testing COBBIE."""

    def count_walls() -> int:
        """Count all wall elements in the IFC model."""
        return 42  # Mock implementation

    def get_building_info() -> dict:
        """Get basic building information."""
        return {
            "name": "Demo Building",
            "floors": 3,
            "area": 1500.5,
            "construction_year": 2020
        }

    return {
        "count_walls": count_walls,
        "get_building_info": get_building_info,
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "web_search": web_search
    }


def demo_basic_functionality():
    """Demonstrate basic COBBIE functionality with metrics."""
    print("🚀 COBBIE Demo: BIM Question Answering with MLflow Tracing")
    print("="*60)

    # Set up MLflow experiment for demo
    experiment_name = "COBBIE_Demo"

    # Check if MLflow server is running, otherwise use SQLite
    try:
        # Try to connect to MLflow server first
        import requests
        requests.get("http://127.0.0.1:5000", timeout=2)
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        print("📊 Connected to MLflow server at http://127.0.0.1:5000")
        print("📊 Traces will be fully visible in the MLflow UI")
    except (requests.RequestException, ImportError):
        # Fallback to SQLite backend
        mlflow.set_tracking_uri("sqlite:///mlflow.sqlite")
        print("📊 Using SQLite MLflow backend (traces will have limited functionality)")
        print("💡 Start MLflow server for full trace viewing: uv run mlflow server --host 127.0.0.1 --port 5000")

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
        final_answer, collector = cobbie_with_metrics(
            user_input=question,
            tools=tools,
            max_iterations=5
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
            print(f"  Total tokens: {(usage.input_tokens or 0) + (usage.output_tokens or 0)}")

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

    print("\n" + "="*60)
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
