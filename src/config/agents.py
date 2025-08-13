"""
Agent Configuration Module

This module contains all hyperparameters and configuration settings for the various agents
in the IFC Answer Engine system. It provides a centralized, hierarchical configuration
structure that eliminates the need to pass numerous parameters through initialization chains.

The configuration is organized by agent type and includes sensible defaults for all parameters.
Users can override specific values as needed without affecting other components.
"""

from typing import Literal, Optional

import dspy
from pydantic import BaseModel, Field, model_validator

from .main import FUNCTION_BOILERPLATE, LANGUAGE_MODELS, LOG_LEVEL


# LLM configuration
class LLMConfig(BaseModel):
    """Configuration for Language Model."""

    model_name: str = Field(
        # default="openrouter-devstral-medium",
        # default="qwen3-coder",
        default="openrouter-qwen3-coder",
        # default="openrouter-gpt-oss-120b",
        description="Name of the model from LANGUAGE_MODELS",
    )
    max_tokens: int = Field(default=2**14, description="Maximum tokens for LLM")

    # Derived cost fields populated after initialization from LANGUAGE_MODELS
    cost_input_token: float = 0
    cost_output_token: float = 0

    @model_validator(mode="after")
    def set_costs_from_language_models(self):
        lm_info = LANGUAGE_MODELS.get(self.model_name)
        if lm_info is not None:
            self.cost_input_token = lm_info.cost_input_token or 0
            self.cost_output_token = lm_info.cost_output_token or 0
        else:
            self.cost_input_token = 0
            self.cost_output_token = 0
        return self

    def get_llm(self) -> dspy.LM:
        """Get configured dspy.LM instance."""
        lm_info = LANGUAGE_MODELS[self.model_name]
        return dspy.LM(
            model=lm_info.url, api_key=lm_info.api_key, max_tokens=self.max_tokens
        )


# Base configuration classes
class BaseAgentConfig(BaseModel):
    """Base configuration for all agents."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = LOG_LEVEL
    max_tokens_logs: int = Field(default=2**12, description="Maximum tokens for logs")
    max_tokens_output: int = Field(
        default=2**12, description="Maximum tokens for output"
    )
    llm: LLMConfig = Field(
        default_factory=LLMConfig, description="Language model configuration"
    )
    load_optimized_model: bool = Field(
        default=True,
        description="Whether to load the optimized model or not.",
    )
    tracking_uri: str = Field(
        default="http://127.0.0.1:5000", description="MLflow tracking URI"
    )


class CodeActConfig(BaseModel):
    """Configuration for CodeAct-based agents."""

    max_iters: int = Field(
        default=10, description="Maximum iterations for CodeAct agents"
    )
    add_code_prefix: bool = Field(
        default=True, description="Whether to add code prefix"
    )


# Individual agent configurations
class ToolProgrammerConfig(BaseAgentConfig, CodeActConfig):
    """Configuration for ToolProgrammer agent."""

    pass  # Inherits all defaults from parent classes


class ToolAssessorConfig(BaseAgentConfig, CodeActConfig):
    """Configuration for ToolAssessor agent."""

    pass  # Inherits all defaults from parent classes


class ToolCorrectorConfig(BaseAgentConfig, CodeActConfig):
    """Configuration for ToolCorrector agent."""

    pass  # Inherits all defaults from parent classes


class ToolIdentifierConfig(BaseAgentConfig):
    """Configuration for FunctionIdentifier agent."""

    pass  # Inherits all defaults from parent class


class ToolOptimizerConfig(BaseAgentConfig):
    """Configuration for ToolOptimizer agent."""

    pass  # Inherits all defaults from parent class


class ErrorAnalystConfig(BaseAgentConfig, CodeActConfig):
    """Configuration for ErrorAnalyst agent."""

    pass  # Inherits all defaults from parent classes


class ToolMergerConfig(BaseAgentConfig, CodeActConfig):
    """Configuration for the ToolMerger agent"""

    pass  # Inherits all defaults from parent classes


class TestAndImproveConfig(BaseAgentConfig, CodeActConfig):
    """Configuration for the TestAndImprove agent"""

    max_iter: int = Field(
        default=3, description="Maximum number of loops of testing and improving."
    )
    add_code_prefix: bool = Field(
        default=True, description="Whether to add code prefix"
    )

    # Sub-agent configurations
    tool_assessor: ToolAssessorConfig = Field(default_factory=ToolAssessorConfig)
    tool_corrector: ToolCorrectorConfig = Field(default_factory=ToolCorrectorConfig)


class ToolDebuggerConfig(BaseAgentConfig):
    """Configuration for ToolDebugger multi-agent system."""

    max_iter: int = Field(
        default=3, description="Maximum iterations for ToolDebugger main loop"
    )
    add_code_prefix: bool = Field(
        default=True, description="Whether to add code prefix"
    )

    # Sub-agent configurations
    tool_assessor: ToolAssessorConfig = Field(default_factory=ToolAssessorConfig)
    tool_corrector: ToolCorrectorConfig = Field(default_factory=ToolCorrectorConfig)


class ToolCreatorConfig(BaseAgentConfig):
    """Configuration for ToolCreator multi-agent system."""

    max_iters: int = Field(
        default=10, description="Maximum iterations for ToolCreator main loop"
    )
    function_boilerplate: str = FUNCTION_BOILERPLATE
    add_code_prefix: bool = Field(
        default=True, description="Whether to add code prefix"
    )

    # Sub-agent configurations
    tool_programmer: ToolProgrammerConfig = Field(default_factory=ToolProgrammerConfig)
    tool_assessor: ToolAssessorConfig = Field(default_factory=ToolAssessorConfig)
    tool_corrector: ToolCorrectorConfig = Field(default_factory=ToolCorrectorConfig)


class IfcAnswerEngineConfig(BaseAgentConfig):
    """Configuration for the main IfcAnswerEngine."""

    max_iters: int = Field(default=10, description="Maximum iterations for main engine")
    max_retry: int = Field(default=2, description="Maximum retry attempts")
    import_all_created_tools: bool = Field(
        default=True, description="Whether to import all created tools"
    )
    add_code_prefix: bool = Field(
        default=True, description="Whether to add code prefix"
    )

    # Tool creator configuration
    tool_creator: ToolCreatorConfig = Field(default_factory=ToolCreatorConfig)


class TrainingModuleConfig(BaseAgentConfig):
    """Configuration for the training module."""

    training_size: Optional[int] = Field(
        default=2, description="Number of training examples"
    )
    similarity_threshold: float = Field(
        default=0.8, description="Similarity threshold for answer verification"
    )

    experiment_name: str = Field(
        default="Training", description="MLflow experiment name"
    )


class TrainingPipelineConfig(BaseAgentConfig):
    """Configuration for the training pipeline"""

    experiment_name: str = Field(
        default="Training", description="MLflow experiment name"
    )
    evaluate: bool = Field(
        default=True,
        description="Evaluate the performance of the system, before and after the training run.",
    )
    optimizer: Literal[
        None,
        "BootStrapFewShot",
    ] = Field(
        default="BootStrapFewShot",
        description="Which Dspy optimizer to use after the training and before the final evaluation.",
    )

    pass


class AnswerVerifierConfig(BaseAgentConfig):
    """Configuration for AnswerVerifier agent."""

    similarity_threshold: float = Field(
        default=0.8, description="Similarity threshold for answer verification"
    )
    # Override LLM default to be consistent with other agents (use default_factory)
    llm: LLMConfig = Field(
        default_factory=lambda: LLMConfig(model_name="openrouter-claude"),
        description="Language model configuration",
    )


# Global configuration instance
class AgentConfigs(BaseModel):
    """Main configuration container for all agents."""

    ifc_answer_engine: IfcAnswerEngineConfig = Field(
        default_factory=IfcAnswerEngineConfig
    )
    tool_creator: ToolCreatorConfig = Field(default_factory=ToolCreatorConfig)
    tool_debugger: ToolDebuggerConfig = Field(default_factory=ToolDebuggerConfig)
    tool_programmer: ToolProgrammerConfig = Field(default_factory=ToolProgrammerConfig)
    tool_assessor: ToolAssessorConfig = Field(default_factory=ToolAssessorConfig)
    tool_corrector: ToolCorrectorConfig = Field(default_factory=ToolCorrectorConfig)
    function_identifier: ToolIdentifierConfig = Field(
        default_factory=ToolIdentifierConfig
    )
    tool_optimizer: ToolOptimizerConfig = Field(default_factory=ToolOptimizerConfig)
    error_analyst: ErrorAnalystConfig = Field(default_factory=ErrorAnalystConfig)
    training_module: TrainingModuleConfig = Field(default_factory=TrainingModuleConfig)
    tool_merger: ToolMergerConfig = Field(default_factory=ToolMergerConfig)
    test_and_improve: TestAndImproveConfig = Field(default_factory=TestAndImproveConfig)
    training_pipeline: TrainingPipelineConfig = Field(
        default_factory=TrainingPipelineConfig
    )
    answer_verifier: AnswerVerifierConfig = Field(default_factory=AnswerVerifierConfig)


# Global instance - this is what gets imported and used
AGENT_CONFIGS = AgentConfigs()


def get_config(agent_name: str) -> BaseAgentConfig:
    """
    Get configuration for a specific agent.

    Args:
        agent_name: Name of the agent ('ifc_answer_engine', 'tool_creator', etc.)

    Returns:
        Configuration object for the specified agent

    Raises:
        ValueError: If agent_name is not recognized
    """
    config_map = {
        "ifc_answer_engine": AGENT_CONFIGS.ifc_answer_engine,
        "tool_creator": AGENT_CONFIGS.tool_creator,
        "tool_debugger": AGENT_CONFIGS.tool_debugger,
        "tool_programmer": AGENT_CONFIGS.tool_programmer,
        "tool_assessor": AGENT_CONFIGS.tool_assessor,
        "tool_corrector": AGENT_CONFIGS.tool_corrector,
        "function_identifier": AGENT_CONFIGS.function_identifier,
        "tool_optimizer": AGENT_CONFIGS.tool_optimizer,
        "error_analyst": AGENT_CONFIGS.error_analyst,
        "training_module": AGENT_CONFIGS.training_module,
        "answer_verifier": AGENT_CONFIGS.answer_verifier,
    }

    if agent_name not in config_map:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(config_map.keys())}"
        )

    return config_map[agent_name]


def update_config(agent_name: str, **kwargs) -> None:
    """
    Update configuration for a specific agent.

    Args:
        agent_name: Name of the agent to update
        **kwargs: Configuration parameters to update

    Example:
        update_config('tool_creator', max_iter=5, log_level='INFO')
    """
    config = get_config(agent_name)
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
        else:
            raise ValueError(
                f"Invalid config parameter '{key}' for agent '{agent_name}'"
            )
