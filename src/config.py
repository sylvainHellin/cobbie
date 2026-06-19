import os
from dotenv import load_dotenv, find_dotenv
from typing import Literal

load_dotenv(find_dotenv())

# Path
ROOT_PATH = os.environ["ROOT_PATH"]
SRC_PATH = os.path.join(ROOT_PATH, "src")
TEST_IFC_PATH = os.path.join(ROOT_PATH, "src/db/bim_models/duplex/arc.ifc")
DB_PATH = os.path.join(ROOT_PATH, "src/db/db.db")
DIRECTORY_IFC_MODELS_PATH = os.path.join(ROOT_PATH, "src/db/bim_models")
CREATED_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/created")
INITIAL_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/initial")
MANUAL_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/manual")

# Provider API keys are read directly from os.environ by the consumers that need
# them (src/harness/llm.py prefix routing, scripts/judge.py). config.py does not
# hard-require them, so a missing optional provider key never blocks import.

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
