#!/usr/bin/env python3

"""
Test BAML implementation with Z.AI GLM 4.6 and an actual IFC file

Setup Instructions:
1. Make sure you have a Z.AI GLM Coding Plan subscription
2. Set Z_AI_API_KEY in your .env file with your Z.AI API key
3. Ensure the IFC model exists at the specified path
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if Z_AI_API_KEY is set
if not os.getenv("Z_AI_API_KEY"):
    print("❌ Error: Z_AI_API_KEY environment variable is not set")
    print("")
    print("Setup Instructions:")
    print("1. Get your Z.AI API key from: https://z.ai/manage-apikey/apikey-list")
    print("2. Add it to your .env file: Z_AI_API_KEY=your_api_key_here")
    print("3. Make sure you have a GLM Coding Plan subscription")
    print("")
    sys.exit(1)

print("✅ Z.AI API key found - using GLM 4.6 with Coding Plan endpoint")

# Import the BAML agent
from src.engine.components.bim_qas import BIM_QAS

# Setup MLflow
import mlflow
import time

mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("BIMQAS_BAML_TEST")

# Path to IFC file
ifc_model_path = "src/db/bim_models/duplex/arc.ifc"

# Test with a simple question
test_question = "How many walls are in the building?"

# Initialize the BAML agent
agent = BIM_QAS(
    max_iterations=3,
    log_level="INFO",
    path_ifc_model=ifc_model_path,
    add_code_prefix=True
)

# Verify IFC model exists
if not os.path.exists(ifc_model_path):
    print(f"❌ Error: IFC model not found at {ifc_model_path}")
    print("Please ensure the IFC model file exists at the specified path")
    sys.exit(1)

print(f"🔧 Testing BAML agent with Z.AI GLM 4.6 (Coding Plan)")
print(f"📁 IFC model: {ifc_model_path}")
print(f"❓ Question: {test_question}")
print("=" * 60)

# Run the test with MLflow tracking
start_time = time.time()

with mlflow.start_run(run_name=f"BAML_Test_{test_question[:30].replace(' ', '_')}") as run:
    # Log parameters
    mlflow.log_param("question", test_question)
    mlflow.log_param("ifc_model_path", ifc_model_path)
    mlflow.log_param("max_iterations", 3)
    mlflow.log_param("llm_provider", "Z.AI")
    mlflow.log_param("llm_model", "GLM-4.6")
    mlflow.log_param("add_code_prefix", True)

    # Run the test
    result = agent.run(test_question)

    execution_time = time.time() - start_time

    # Log metrics
    mlflow.log_metric("execution_time_seconds", execution_time)
    mlflow.log_metric("iterations_used", result.get("iterations", 0))

    success_status = 1 if result.get("status") == "success" else 0
    mlflow.log_metric("success_status", success_status)

    # Log results as parameters
    if result.get("status") == "success":
        mlflow.log_param("final_answer", result.get("answer", ""))
        mlflow.log_param("reasoning", result.get("reasoning", ""))
    else:
        mlflow.log_param("error_message", result.get("error", "Unknown error"))

print("\n📊 RESULT:")
print("=" * 60)
for key, value in result.items():
    print(f"{key}: {value}")

if result.get("status") == "success":
    print("\n✅ Test completed successfully with Z.AI GLM 4.6!")
    print(f"🔄 Completed in {result.get('iterations', 'unknown')} iterations")
    if "reasoning" in result:
        print(f"💭 Model reasoning: {result['reasoning']}")
else:
    print(f"\n❌ Test completed with status: {result.get('status')}")
    if "error" in result:
        print(f"🚨 Error details: {result['error']}")
