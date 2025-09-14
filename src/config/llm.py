"""
LLM Configuration and Registry Module

This module provides centralized management of language models, their configurations, and providers.
It supports multiple LLM providers (Anthropic, OpenAI, Gemini, DeepSeek, Groq, etc.) and models,
with automatic cost tracking and dspy integration.

Available Classes:
- LLMProvider: Configuration for an LLM provider (name, base_url, API key)
- LLMModel: Configuration for a specific model (name, model_path, default max_tokens)
- ModelAvailability: Maps models to providers with pricing information
- LLMRegistry: Central registry managing all providers, models, and availability
- LLM: High-level configuration class for agents with cost and provider properties

Usage Examples:
    # Basic usage with default provider
    llm_config = LLM(model_name="qwen3-coder")
    dspy_llm = llm_config.get_llm()

    # Specify provider explicitly
    llm_config = LLM(model_name="claude-sonnet-4", provider_name="anthropic")

    # Access cost information
    input_cost = llm_config.cost_input_token
    output_cost = llm_config.cost_output_token

    # List available models and providers
    all_models = LLM_REGISTRY.list_models()
    providers_for_model = LLM_REGISTRY.list_providers_for_model("qwen3-coder")

    # Direct registry usage
    model, provider, availability = LLM_REGISTRY.get_model_info("gemini-flash", "gemini")
    dspy_llm = LLM_REGISTRY.create_dspy_llm("deepseek-chat", "deepseek")

The module automatically loads API keys from environment variables and provides
cost-aware model selection for different providers.
"""

import os
from typing import Dict, List, Optional, Tuple

import dspy
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field

_ = load_dotenv(find_dotenv())


class LLMProvider(BaseModel):
    """Configuration for an LLM provider."""

    name: str
    base_url: str
    api_key_env_var: str
    api_key: str = ""

    def model_post_init(self, __context):
        """Load API key from environment."""
        if self.api_key_env_var:
            self.api_key = os.getenv(self.api_key_env_var, "")


class LLMModel(BaseModel):
    """Configuration for a specific LLM model."""

    name: str
    model_path: str  # The actual model identifier used by the provider
    max_tokens_default: int = 2**14


class ModelAvailability(BaseModel):
    """Represents a model available through a specific provider with specific pricing."""

    model_name: str
    provider_name: str
    cost_input_token: Optional[float] = None
    cost_output_token: Optional[float] = None
    model_path_override: Optional[str] = None  # Override model path for this provider


class LLMRegistry:
    """Registry for managing LLM providers and models."""

    def __init__(self):
        self.providers: Dict[str, LLMProvider] = {}
        self.models: Dict[str, LLMModel] = {}
        self.availability: List[ModelAvailability] = []
        self._setup_default_providers()
        self._setup_default_models()
        self._setup_model_availability()

    def _setup_default_providers(self):
        """Setup default LLM providers."""
        providers = [
            LLMProvider(
                name="anthropic",
                base_url="anthropic",
                api_key_env_var="ANTHROPIC_API_KEY",
            ),
            LLMProvider(
                name="openai", base_url="openai", api_key_env_var="OPENAI_API_KEY"
            ),
            LLMProvider(
                name="gemini", base_url="gemini", api_key_env_var="GEMINI_API_KEY"
            ),
            LLMProvider(
                name="deepseek", base_url="deepseek", api_key_env_var="DEEPSEEK_API_KEY"
            ),
            LLMProvider(name="groq", base_url="groq", api_key_env_var="GROQ_API_KEY"),
            LLMProvider(
                name="mistral", base_url="mistral", api_key_env_var="MISTRAL_API_KEY"
            ),
            LLMProvider(
                name="fireworks",
                base_url="fireworks_ai",
                api_key_env_var="FIREWORKS_API_KEY",
            ),
            LLMProvider(
                name="cerebras", base_url="cerebras", api_key_env_var="CEREBRAS_API_KEY"
            ),
            LLMProvider(
                name="openrouter",
                base_url="openrouter",
                api_key_env_var="OPENROUTER_API_KEY",
            ),
            LLMProvider(name="ollama", base_url="ollama_chat", api_key_env_var=""),
            LLMProvider(
                name="deepinfra",
                base_url="deepinfra",
                api_key_env_var="DEEPINFRA_API_KEY",
            ),
        ]

        for provider in providers:
            self.providers[provider.name] = provider

    def _setup_default_models(self):
        """Setup base model definitions."""
        models = [
            # Base models (without provider-specific details)
            LLMModel(name="gemini-flash", model_path="gemini-2.5-flash"),
            LLMModel(name="gemini-pro", model_path="gemini-2.5-pro-preview-05-06"),
            LLMModel(name="deepseek-chat", model_path="deepseek-chat"),
            LLMModel(name="llama-3.3-70b", model_path="llama-3.3-70b-versatile"),
            LLMModel(name="kimi-k2", model_path="moonshotai/kimi-k2-instruct"),
            LLMModel(
                name="llama-4-maverick",
                model_path="meta-llama/llama-4-maverick-17b-128e-instruct",
            ),
            LLMModel(name="llama-4-scout", model_path="llama-4-scout-17b-16e-instruct"),
            LLMModel(name="qwen3-coder", model_path="qwen3-coder"),
            LLMModel(
                name="qwen3-235b",
                model_path="accounts/fireworks/models/qwen3-235b-a22b",
            ),
            LLMModel(name="devstral-medium", model_path="devstral-medium-2507"),
            LLMModel(name="codestral", model_path="codestral-2508"),
            LLMModel(name="claude-sonnet-4", model_path="claude-sonnet-4-20250514"),
            LLMModel(name="gpt-oss-120b", model_path="openai/gpt-oss-120b"),
            LLMModel(
                name="gemini-flash-lite", model_path="google/gemini-2.5-flash-lite"
            ),
            LLMModel(name="qwen3-coder:30b", model_path="qwen3-coder:30b"),
            LLMModel(name="gemma3-12b", model_path="gemma3:12b"),
            LLMModel(name="qwen3:8b", model_path="qwen3:8b"),
            LLMModel(name="gemma3-4b", model_path="gemma3:4b"),
            LLMModel(name="gemma3n", model_path="gemma3n:e4b"),
            LLMModel(
                name="qwen3-coder-turbo",
                model_path="Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo",
            ),
        ]

        for model in models:
            self.models[model.name] = model

    def _setup_model_availability(self):
        """Setup which models are available through which providers and their costs."""
        availability = [
            # Gemini models
            ModelAvailability(model_name="gemini-flash", provider_name="gemini"),
            ModelAvailability(model_name="gemini-pro", provider_name="gemini"),
            ModelAvailability(
                model_name="gemini-flash-lite",
                provider_name="openrouter",
                cost_input_token=0.1,
                cost_output_token=0.4,
            ),
            # DeepSeek
            ModelAvailability(model_name="deepseek-chat", provider_name="deepseek"),
            # Groq models
            ModelAvailability(model_name="llama-3.3-70b", provider_name="groq"),
            ModelAvailability(model_name="kimi-k2", provider_name="groq"),
            ModelAvailability(model_name="llama-4-maverick", provider_name="groq"),
            # Cerebras
            ModelAvailability(model_name="llama-4-scout", provider_name="cerebras"),
            # Fireworks
            ModelAvailability(
                model_name="llama-3.3-70b",
                provider_name="fireworks",
                model_path_override="accounts/fireworks/models/llama-v3p3-70b-isntruct",
            ),
            ModelAvailability(model_name="qwen3-235b", provider_name="fireworks"),
            # Mistral
            ModelAvailability(
                model_name="devstral-medium",
                provider_name="mistral",
                cost_input_token=0.4,
                cost_output_token=2.0,
            ),
            ModelAvailability(
                model_name="codestral",
                provider_name="mistral",
                cost_input_token=0.3,
                cost_output_token=0.9,
            ),
            # Claude
            ModelAvailability(model_name="claude-sonnet-4", provider_name="anthropic"),
            ModelAvailability(
                model_name="claude-sonnet-4",
                provider_name="openrouter",
                model_path_override="anthropic/claude-sonnet-4",
                cost_input_token=3.0,
                cost_output_token=15.0,
            ),
            # OpenRouter exclusive models
            ModelAvailability(
                model_name="gpt-oss-120b",
                provider_name="openrouter",
                cost_input_token=0.1,
                cost_output_token=0.5,
            ),
            # Models available through multiple providers
            ModelAvailability(
                model_name="qwen3-coder",
                provider_name="openrouter",
                model_path_override="qwen/qwen3-coder",
                cost_input_token=0.3,
                cost_output_token=1.2,
            ),
            ModelAvailability(
                model_name="qwen3-coder",
                provider_name="openrouter",
                model_path_override="cerebras/qwen3-coder",
                cost_input_token=2.0,
                cost_output_token=2.0,
            ),
            ModelAvailability(
                model_name="qwen3-coder",
                provider_name="ollama",
            ),
            ModelAvailability(
                model_name="qwen3-coder",
                provider_name="deepinfra",
                model_path_override="Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo",
                cost_input_token=0.3,
                cost_output_token=1.2,
            ),
            ModelAvailability(
                model_name="devstral-medium",
                provider_name="openrouter",
                model_path_override="mistralai/devstral-medium",
                cost_input_token=0.4,
                cost_output_token=2.0,
            ),
            # Ollama models
            ModelAvailability(model_name="qwen3-coder:30b", provider_name="ollama"),
            ModelAvailability(model_name="gemma3-12b", provider_name="ollama"),
            ModelAvailability(model_name="qwen3:8b", provider_name="ollama"),
            ModelAvailability(model_name="gemma3-4b", provider_name="ollama"),
            ModelAvailability(model_name="gemma3n", provider_name="ollama"),
        ]

        self.availability = availability

    def get_model_info(
        self, model_name: str, provider_name: str = ""
    ) -> Tuple[LLMModel, LLMProvider, ModelAvailability]:
        """Get complete information about a model and provider combination."""
        # Get base model
        if model_name not in self.models:
            raise ValueError(
                f"Model '{model_name}' not found. Available: {list(self.models.keys())}"
            )
        model = self.models[model_name]

        # Find available providers for this model
        available = [a for a in self.availability if a.model_name == model_name]
        if not available:
            raise ValueError(
                f"Model '{model_name}' is not available through any provider"
            )

        # If no provider specified, use the first available
        if provider_name is None:
            availability = available[0]
            provider_name = availability.provider_name
        else:
            # Find the specific provider
            availability = next(
                (a for a in available if a.provider_name == provider_name), None
            )
            if availability is None:
                available_providers = [a.provider_name for a in available]
                raise ValueError(
                    f"Model '{model_name}' not available through provider '{provider_name}'. Available providers: {available_providers}"
                )

        # Get provider
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' not found")
        provider = self.providers[provider_name]

        return model, provider, availability

    def create_dspy_llm(
        self,
        model_name: str,
        provider_name: str = "",
        max_tokens: Optional[int] = None,
    ) -> dspy.LM:
        """Create a dspy.LM instance for the specified model and provider."""
        model, provider, availability = self.get_model_info(model_name, provider_name)

        # Use override path if specified, otherwise use base model path
        model_path = availability.model_path_override or model.model_path
        full_url = f"{provider.base_url}/{model_path}"

        max_tokens = max_tokens or model.max_tokens_default

        return dspy.LM(model=full_url, api_key=provider.api_key, max_tokens=max_tokens)

    def get_costs(
        self, model_name: str, provider_name: str = ""
    ) -> Tuple[float, float]:
        """Get input and output token costs for a model-provider combination."""
        _, _, availability = self.get_model_info(model_name, provider_name)
        return (
            availability.cost_input_token or 0.0,
            availability.cost_output_token or 0.0,
        )

    def list_models(self, provider_name: str = "") -> List[str]:
        """List all available models, optionally filtered by provider."""
        if provider_name:
            return [
                a.model_name
                for a in self.availability
                if a.provider_name == provider_name
            ]
        return list(set(a.model_name for a in self.availability))

    def list_providers_for_model(self, model_name: str) -> List[str]:
        """List all providers that offer a specific model."""
        return [
            a.provider_name for a in self.availability if a.model_name == model_name
        ]


# Global registry instance
LLM_REGISTRY = LLMRegistry()


class LLM(BaseModel):
    """LLM configuration for agents."""

    # Uncomment for using Cloud model
    model_name: str = Field(default="qwen3-coder", description="Name of the model")
    provider_name: str = Field(
        default="deepinfra",
        description="Provider to use (auto-selected if None)",
    )

    # Uncomment for using local model
    # model_name: str = Field(default="qwen3-coder:30b", description="Name of the model")
    # provider_name: str = Field(
    #     default="ollama",
    #     description="Provider to use (auto-selected if None)",
    # )
    max_tokens: int = Field(default=2**14, description="Maximum tokens for LLM")

    @property
    def cost_input_token(self) -> float:
        """Get input token cost for the model-provider combination."""
        input_cost, _ = LLM_REGISTRY.get_costs(self.model_name, self.provider_name)
        return input_cost

    @property
    def cost_output_token(self) -> float:
        """Get output token cost for the model-provider combination."""
        _, output_cost = LLM_REGISTRY.get_costs(self.model_name, self.provider_name)
        return output_cost

    def get_llm(self) -> dspy.LM:
        """Get configured dspy.LM instance."""
        return LLM_REGISTRY.create_dspy_llm(
            self.model_name, self.provider_name, self.max_tokens
        )

    @property
    def available_providers(self) -> List[str]:
        """Get list of providers that offer this model."""
        return LLM_REGISTRY.list_providers_for_model(self.model_name)
