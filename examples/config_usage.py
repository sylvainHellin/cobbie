"""
Example: Using the New Configuration System

This example demonstrates how to use the new hierarchical configuration system
for the IFC Answer Engine. It shows how to:
1. Use default configurations
2. Override specific parameters
3. Create custom configurations for different use cases
"""

import dspy
from src.config import AGENT_CONFIGS, LANGUAGE_MODELS, update_config
from src.engine import IfcAnswerEngine
from src.experiment.training.training import TrainingModule


def example_default_configuration():
    """Example using default configuration."""
    print("=== Example 1: Default Configuration ===")

    # Create engine with default config - LLM comes from config!
    engine = IfcAnswerEngine()

    print(f"Engine max_iters: {engine.max_iters}")
    print(f"Engine log_level: {engine.log_level}")
    print(f"Tool creator max_iter: {engine.tool_creator.max_iters}")
    print(f"Tool programmer max_iters: {engine.tool_creator.tool_programmer.max_iters}")


def example_override_specific_parameters():
    """Example overriding specific parameters."""
    print("\n=== Example 2: Override Specific Parameters ===")

    # Update specific configuration values
    update_config("ifc_answer_engine", max_retry=5, log_level="INFO")
    update_config("tool_creator", max_iter=5)
    update_config("tool_programmer", max_iters=15)

    # You can also update LLM config
    from src.config.agents import LLMConfig

    AGENT_CONFIGS.ifc_answer_engine.llm = LLMConfig(
        model_name="gemini-flash", max_tokens=8000
    )

    # Create engine - will use updated configs
    engine = IfcAnswerEngine()

    print(f"Engine max_retry: {engine.max_retry}")  # Should be 5
    print(f"Engine log_level: {engine.log_level}")  # Should be INFO
    print(f"Tool creator max_iter: {engine.tool_creator.max_iters}")  # Should be 5
    print(
        f"Tool programmer max_iters: {engine.tool_creator.tool_programmer.max_iters}"
    )  # Should be 15


def example_custom_configuration():
    """Example using custom configuration objects."""
    print("\n=== Example 3: Custom Configuration ===")

    from src.config.agents import (
        IfcAnswerEngineConfig,
        ToolCreatorConfig,
        ToolProgrammerConfig,
    )

    # Create custom configurations
    custom_programmer_config = ToolProgrammerConfig(
        max_iters=20, log_level="DEBUG", add_code_prefix=False
    )

    custom_tool_creator_config = ToolCreatorConfig(
        max_iters=3, log_level="INFO", tool_programmer=custom_programmer_config
    )

    custom_engine_config = IfcAnswerEngineConfig(
        max_iters=15,
        max_retry=3,
        log_level="WARNING",
        tool_creator=custom_tool_creator_config,
    )

    # Create engine with custom config
    engine = IfcAnswerEngine(config=custom_engine_config)

    print(f"Engine max_iters: {engine.max_iters}")  # Should be 15
    print(f"Engine log_level: {engine.log_level}")  # Should be WARNING
    print(f"Tool creator max_iter: {engine.tool_creator.max_iters}")  # Should be 2
    print(
        f"Tool programmer max_iters: {engine.tool_creator.tool_programmer.max_iters}"
    )  # Should be 20
    print(
        f"Tool programmer add_code_prefix: {engine.tool_creator.tool_programmer.add_code_prefix}"
    )  # Should be False


def example_training_module():
    """Example using TrainingModule with config."""
    print("\n=== Example 4: Training Module Configuration ===")

    # Create training module with default config - much cleaner than before!
    training_module = TrainingModule()

    print(f"Training size: {training_module.training_size}")
    print(f"Similarity threshold: {training_module.similarity_treshold}")
    print(f"Tracking URI: {training_module.tracking_uri}")
    print(f"Engine max_retry: {training_module.engine.max_retry}")


if __name__ == "__main__":
    example_default_configuration()
    example_override_specific_parameters()
    example_custom_configuration()
    example_training_module()

    print("\n=== Benefits of New Configuration System ===")
    print("✅ No more parameter passing through multiple levels")
    print("✅ Centralized configuration management")
    print("✅ Easy to override specific parameters")
    print("✅ Type-safe configuration with Pydantic")
    print("✅ Clear separation of concerns")
    print("✅ Much cleaner initialization code")
