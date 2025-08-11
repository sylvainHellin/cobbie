import os
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel
from typing import Literal

load_dotenv(find_dotenv())

# Path
ROOT_PATH = os.environ["ROOT_PATH"]
SRC_PATH = os.path.join(ROOT_PATH, "src")
TEST_IFC_PATH = os.path.join(ROOT_PATH, "src/experiment/bim_models/duplex/arc.ifc")
DATASET_PATH = os.path.join(SRC_PATH, "experiment/datasets", "ifc-bench-v1.1.csv")
VECTORSTORE_PATH = os.path.join(ROOT_PATH, "src/engine/tools/primordial/vectorstore")
DB_PATH = os.path.join(ROOT_PATH, "src/experiment/db/db.db")
CSV_IFC_MODELS_PATH = os.path.join(ROOT_PATH, "src/experiment/db/ifc_models.csv")
DIRECTORY_IFC_MODELS_PATH = os.path.join(ROOT_PATH, "src/experiment/bim_models")
CREATED_TOOLS_PATH = os.path.join(ROOT_PATH, "src/engine/tools/created")
CHECKPOINT_PATH = os.path.join(ROOT_PATH, "src/experiment/training/.checkpoint")
OPTIMIZED_MODEL_PATH = os.path.join(ROOT_PATH, "src/engine/optimizer/engine.json")

# URI
MLFLOW_URI = "http://127.0.0.1:5000"

# Load the overview of the documentation of IfcOpenShell
doc_path = os.path.join(
    ROOT_PATH, "src/engine/tools/primordial/ifcopenshell_api_overview.md"
)
with open(doc_path, "r") as file:
    IFCOPENSHELL_DOCUMENTATION_OVERVIEW = file.read()
del doc_path

# loads secrets
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
FIREWORKS_API_KEY = os.environ["FIREWORKS_API_KEY"]
CEREBRAS_API_KEY = os.environ["CEREBRAS_API_KEY"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]


# Set up language model (LiteLLM endpoints)
class LLM(BaseModel):
    url: str
    name: str
    api_key: str = ""


LANGUAGE_MODELS: dict[str, LLM] = {}

LANGUAGE_MODELS["gemini-flash"] = LLM(
    url="gemini/gemini-2.5-flash", api_key=GEMINI_API_KEY, name="gemini-flash"
)
LANGUAGE_MODELS["gemini-pro"] = LLM(
    url="gemini/gemini-2.5-pro-preview-05-06", api_key=GEMINI_API_KEY, name="gemini-pro"
)
LANGUAGE_MODELS["deepseek-v3"] = LLM(
    url="deepseek/deepseek-chat", api_key=DEEPSEEK_API_KEY, name="deepseek-v3"
)
LANGUAGE_MODELS["llama3-70b-groq"] = LLM(
    url="groq/llama-3.3-70b-versatile", api_key=GROQ_API_KEY, name="llama3-70b-groq"
)
LANGUAGE_MODELS["kimi-k2"] = LLM(
    url="groq/moonshotai/kimi-k2-instruct", api_key=GROQ_API_KEY, name="kimi-k2"
)
LANGUAGE_MODELS["llama4-maverick-groq"] = LLM(
    url="groq/meta-llama/llama-4-maverick-17b-128e-instruct",
    api_key=GROQ_API_KEY,
    name="llama4-maverick-groq",
)
LANGUAGE_MODELS["llama4-scout-cerebras"] = LLM(
    url="cerebras/llama-4-scout-17b-16e-instruct",
    api_key=CEREBRAS_API_KEY,
    name="llama4-scout-cerebras",
)
LANGUAGE_MODELS["llama3-70b-fireworks"] = LLM(
    url="fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-isntruct",
    api_key=FIREWORKS_API_KEY,
    name="llama3-70b-fireworks",
)
LANGUAGE_MODELS["qwen3-235b-fireworks"] = LLM(
    url="fireworks_ai/accounts/fireworks/models/qwen3-235b-a22b",
    api_key=FIREWORKS_API_KEY,
    name="qwen3-235b-fireworks",
)
LANGUAGE_MODELS["qwen3-30b-ollama"] = LLM(
    url="ollama_chat/qwen3:30b", name="qwen3-30b-ollama"
)
LANGUAGE_MODELS["gemma3-12b"] = LLM(
    url="ollama_chat/gemma3:12b",
    name="gemma3-12b",
)
LANGUAGE_MODELS["qwen3-8b"] = LLM(url="ollama_chat/qwen3:8b", name="qwen3-8b")
LANGUAGE_MODELS["gemma3-4b"] = LLM(url="ollama_chat/gemma3:4b", name="gemma3-4b")
LANGUAGE_MODELS["gemma3n"] = LLM(
    url="ollama_chat/gemma3n:e4b",
    name="gemma3n",
)
LANGUAGE_MODELS["devstral-medium"] = LLM(
    url="mistral/devstral-medium-2507",
    api_key=MISTRAL_API_KEY,
    name="devstral-medium",
)
LANGUAGE_MODELS["codestral"] = LLM(
    url="mistral/codestral-2508",
    api_key=MISTRAL_API_KEY,
    name="codestral",
)
LANGUAGE_MODELS["claude"] = LLM(
    url="anthropic/claude-sonnet-4-20250514",
    api_key=ANTHROPIC_API_KEY,
    name="claude",
)


# OpenRouter models
LANGUAGE_MODELS["qwen3-coder"] = LLM(
    url="openrouter/qwen/qwen3-coder",
    api_key=OPENROUTER_API_KEY,
    name="qwen3-coder",
)
LANGUAGE_MODELS["gpt-oss-120b"] = LLM(
    url="openrouter/openai/gpt-oss-120b",
    api_key=OPENROUTER_API_KEY,
    name="gpt-oss-120b",
)
LANGUAGE_MODELS["gemini-flash-lite"] = LLM(
    url="openrouter/google/gemini-2.5-flash-lite",
    api_key=OPENROUTER_API_KEY,
    name="gemini-flash-lite",
)
LANGUAGE_MODELS["qwen3-coder-cerebras"] = LLM(
    url="openrouter/cerebras/qwen3-coder",
    api_key=OPENROUTER_API_KEY,
    name="qwen3-coder-cerebras",
)
LANGUAGE_MODELS["openrouter-claude"] = LLM(
    url="openrouter/anthropic/claude-sonnet-4",
    api_key=OPENROUTER_API_KEY,
    name="claude",
)
LANGUAGE_MODELS["openrouter-devstral-medium"] = LLM(
    url="openrouter/mistralai/devstral-medium",
    api_key=OPENROUTER_API_KEY,
    name="devstral=medium",
)
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
FUNCTION_BOILERPLATE = """
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *
"""

# Configure logger
LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
