#!/usr/bin/env python3

"""
Test BAML implementation with an actual IFC file
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if OPENAI_API_KEY is set
if not os.getenv("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable is not set")
    sys.exit(1)

# Import the BAML agent
from src.engine.components.code_act_agent_baml import BIMQASBaml

# Setup MLflow
import mlflow
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("BIMQAS_BAML_TEST")

# Path to IFC file
ifc_model_path = "src/experiment/bim_models/duplex/arc.ifc"

# Test with a simple question
test_question = "How many walls are in the building?"

# Initialize the BAML agent
agent = BIMQASBaml(
    max_iterations=3,
    log_level="INFO",
    path_ifc_model=ifc_model_path,
    add_code_prefix=True
)

print(f"🔧 Testing BAML agent with IFC model: {ifc_model_path}")
print(f"❓ Question: {test_question}")
print("=" * 60)

# Run the test
result = agent.run(test_question)

print("\n📊 RESULT:")
print("=" * 60)
for key, value in result.items():
    print(f"{key}: {value}")

if result.get("status") == "success":
    print("\n✅ Test completed successfully!")
else:
    print(f"\n❌ Test completed with status: {result.get('status')}")
