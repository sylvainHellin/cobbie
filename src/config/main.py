import os
from dotenv import load_dotenv, find_dotenv
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
PATH_COMPILED_MODEL = os.path.join(ROOT_PATH, "src/engine/optimizer/engine.json")

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
