import os
from dotenv import load_dotenv, find_dotenv
from smolagents import LiteLLMModel

load_dotenv(find_dotenv())

# Get the src directory path
ROOT_PATH = os.environ["ROOT_PATH"]
SRC_PATH = os.path.join(ROOT_PATH, "src")
TEST_IFC_PATH = os.path.join(SRC_PATH, "bim_models/duplex/arc.ifc")

# PATH
DATASET_PATH = os.path.join(SRC_PATH, "datasets", "ifc-bench-v1.csv")
RESULTS_CHECKPOINT_PATH = os.path.join(SRC_PATH, "results", "checkpoint.json")
OUTPUT_PATH = output_path = os.path.join(SRC_PATH, "results", "benchmark_results.xlsx")
VECTORSTORE_PATH = os.path.join(SRC_PATH, "special_tools/vectorstore")

# loads secrets
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
FIREWORKS_API_KEY = os.environ["FIREWORKS_API_KEY"]
CEREBRAS_API_KEY = os.environ["CEREBRAS_API_KEY"]

# Set up language model (LiteLLM endpoints)
LANGUAGE_MODELS = {
    "claude": LiteLLMModel(
        "anthropic/claude-3-7-sonnet-latest", api_key=ANTHROPIC_API_KEY
    ),
    "gemini_flash": LiteLLMModel("gemini/gemini-2.0-flash", api_key=GEMINI_API_KEY),
    "gemini_pro": LiteLLMModel(
        "gemini/gemini-2.5-pro-preview-05-06", api_key=GEMINI_API_KEY
    ),
    "deepseek": LiteLLMModel("deepseek/deepseek-chat", api_key=DEEPSEEK_API_KEY),
    "llama_3.1_8b": LiteLLMModel("groq/llama-3.1-8b-instant", api_key=GROQ_API_KEY),
    "llama_3.3_70b": LiteLLMModel("groq/llama-3.3-70b-versatile", api_key=GROQ_API_KEY),
    "llama_3.3_70b_fireworks": LiteLLMModel(
        "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct",
        api_key=FIREWORKS_API_KEY,
    ),
    "qwen3_235b": LiteLLMModel(
        "fireworks_ai/accounts/fireworks/models/qwen3-235b-a22b",
        api_key=FIREWORKS_API_KEY,
    ),
    "gemma_9b": LiteLLMModel("ollama_chat/gemma2:9b-instruct-q8_0"),
    "phi4": LiteLLMModel("ollama_chat/phi4:latest"),
    "qwen3_30b": LiteLLMModel("ollama_chat/qwen3:30b"),
    "mistral": LiteLLMModel("mistral/mistral-medium-latest"),
    "openai": LiteLLMModel("openai/gpt-4o", api_key=OPENAI_API_KEY),
    "llama4_scout": LiteLLMModel(
        "cerebras/llama-4-scout-17b-16e-instruct", api_key=CEREBRAS_API_KEY
    ),
    "llama4_maverick": LiteLLMModel(
        "groq/meta-llama/llama-4-maverick-17b-128e-instruct", api_key=GROQ_API_KEY
    ),
}

# Default models to test in comparisons
MODELS_TO_TEST = [
    "deepseek",
    "claude",
    "gemini",
    "llama_3.3_70b_fireworks",
    "gemma_9b",
    "mistral",
    "openai",
]

# Boilerplate code for the toolmaker
BOILERPLATE = """
import sys
import os

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import ifcopenshell.file
import ifcopenshell.entity_instance

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# Start the function implementation here
"""
