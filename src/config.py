import os
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel

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
class LLM(BaseModel):
    url: str
    api_key: str = ""


LANGUAGE_MODELS: dict[str, LLM] = {}
LANGUAGE_MODELS["claude"] = LLM(
    url="anthropic/claude-3-7-sonnet-latest", api_key=ANTHROPIC_API_KEY
)
LANGUAGE_MODELS["gemini-flash"] = LLM(
    url="gemini/gemini-2.0-flash", api_key=GEMINI_API_KEY
)
LANGUAGE_MODELS["gemini-pro"] = LLM(
    url="gemini/gemini-2.5-pro-preview-05-06", api_key=GEMINI_API_KEY
)
LANGUAGE_MODELS["deepseek-v3"] = LLM(
    url="deepseek/deepseek-chat", api_key=DEEPSEEK_API_KEY
)
LANGUAGE_MODELS["llama3-70b-groq"] = LLM(
    url="groq/llama-3.3-70b-versatile", api_key=GROQ_API_KEY
)
LANGUAGE_MODELS["llama4-maverick-groq"] = LLM(
    url="groq/meta-llama/llama-4-maverick-17b-128e-instruct", api_key=GROQ_API_KEY
)
LANGUAGE_MODELS["llama4-scout-cerebras"] = LLM(
    url="cerebras/llama-4-scout-17b-16e-instruct", api_key=CEREBRAS_API_KEY
)
LANGUAGE_MODELS["llama3-70b-fireworks"] = LLM(
    url="fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-isntruct",
    api_key=FIREWORKS_API_KEY,
)
LANGUAGE_MODELS["qwen3-235b-fireworks"] = LLM(
    url="fireworks_ai/accounts/fireworks/models/qwen3-235b-a22b",
    api_key=FIREWORKS_API_KEY,
)
LANGUAGE_MODELS["qwen3-30b-ollama"] = LLM(url="ollama_chat/qwen3:30b")

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
