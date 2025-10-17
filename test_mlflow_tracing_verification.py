#!/usr/bin/env python3

"""
Quick verification script for MLflow tracing implementation
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if Z_AI_API_KEY is set
if not os.getenv("Z_AI_API_KEY"):
    print("❌ Error: Z_AI_API_KEY environment variable is not set")
    sys.exit(1)

# Setup MLflow
import mlflow
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("BIMQAS_BAML_Tracing_Verification")

# Import the BAML agent
from src.engine.components.bim_qas import BIM_QAS

# Path to IFC file
ifc_model_path = "src/experiment/bim_models/duplex/arc.ifc"

# Test with a simple question
test_question = "How many walls are in the building?"

# Initialize the BAML agent
agent = BIM_QAS(
    max_iterations=2,  # Reduced for quick testing
    log_level="INFO",
    path_ifc_model=ifc_model_path,
    add_code_prefix=True
)

# Verify IFC model exists
if not os.path.exists(ifc_model_path):
    print(f"❌ Error: IFC model not found at {ifc_model_path}")
    sys.exit(1)

print("🔧 Verifying MLflow tracing implementation")
print(f"📁 IFC model: {ifc_model_path}")
print(f"❓ Question: {test_question}")
print("=" * 60)

# Run the test with MLflow tracking
import time
start_time = time.time()

with mlflow.start_run(run_name=f"Tracing_Verification_{int(time.time())}") as run:
    # Log parameters
    mlflow.log_param("test_type", "MLflow_tracing_verification")
    mlflow.log_param("question", test_question)
    mlflow.log_param("ifc_model_path", ifc_model_path)
    mlflow.log_param("max_iterations", 2)
    mlflow.log_param("llm_provider", "Z.AI")
    mlflow.log_param("llm_model", "GLM-4.6")

    # Run the test
    result = agent.run(test_question)

    execution_time = time.time() - start_time

    # Log metrics
    mlflow.log_metric("execution_time_seconds", execution_time)
    mlflow.log_metric("iterations_used", result.get("iterations", 0))
    success_status = 1 if result.get("status") == "success" else 0
    mlflow.log_metric("success_status", success_status)

    # Log results
    if result.get("status") == "success":
        mlflow.log_param("final_answer", result.get("answer", ""))
        mlflow.log_param("reasoning", result.get("reasoning", ""))
    else:
        mlflow.log_param("error_message", result.get("error", "Unknown error"))

    print(f"\n📊 EXECUTION SUMMARY:")
    print("=" * 60)
    print(f"Status: {result.get('status')}")
    print(f"Execution time: {execution_time:.2f} seconds")
    print(f"Iterations used: {result.get('iterations', 0)}")
    print(f"MLflow Run ID: {run.info.run_id}")
    print(f"MLflow URL: http://127.0.0.1:5000/#/experiments/{run.info.experiment_id}/runs/{run.info.run_id}")

print("\n✅ MLflow tracing verification completed!")
print(f"🌐 View traces at: http://127.0.0.1:5000")
