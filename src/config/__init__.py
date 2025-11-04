"""Configuration package for the IFC Answer Engine."""

# Import main config items individually
from .main import (
    ROOT_PATH,
    SRC_PATH,
    TEST_IFC_PATH,
    VECTORSTORE_PATH,
    DB_PATH,
    CSV_IFC_MODELS_PATH,
    DIRECTORY_IFC_MODELS_PATH,
    CREATED_TOOLS_PATH,
    PATH_COMPILED_MODEL,
    MLFLOW_URI,
    FUNCTION_BOILERPLATE,
    LOG_LEVEL,
)
from .agents import AGENT_CONFIGS, get_config, update_config, AgentConfigs, IfcAnswerEngineConfig
from .llm import LLM, LLM_REGISTRY

__all__ = [
    # From main config
    "ROOT_PATH",
    "SRC_PATH",
    "TEST_IFC_PATH",
    "VECTORSTORE_PATH",
    "DB_PATH",
    "CSV_IFC_MODELS_PATH",
    "DIRECTORY_IFC_MODELS_PATH",
    "CREATED_TOOLS_PATH",
    "PATH_COMPILED_MODEL",
    "MLFLOW_URI",
    "FUNCTION_BOILERPLATE",
    "LOG_LEVEL",
    # From agents config
    "AGENT_CONFIGS",
    "get_config",
    "update_config",
    "AgentConfigs",
    "IfcAnswerEngineConfig",
    # From llm config
    "LLM",
    "LLM_REGISTRY",
]
