#!/usr/bin/env python3
"""
Test script for the BAML ToolCreator implementation with comprehensive MLflow tracing.
"""

import os
import sys
import time
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_baml_tool_creator():
    """Test the BAML ToolCreator with a simple function requirement."""

    # Load environment variables
    load_dotenv()

    # Setup MLflow
    import mlflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("ToolCreator_BAML_Test")

    # Import our components
    try:
        from src.engine.components.tool_creator_baml import ToolCreatorBAML
        from src.config.main import TEST_IFC_PATH
        print("✓ Successfully imported BAML ToolCreator")
    except ImportError as e:
        print(f"✗ Failed to import BAML ToolCreator: {e}")
        return False

    # Test data
    function_requirements = """
    Create a function that counts the total number of doors in an IFC model.
    The function should:
    1. Take an IFC file path as input
    2. Open the IFC model using ifcopenshell
    3. Find all door elements (IfcDoor)
    4. Return the count as an integer (not as a string)

    The function should handle errors gracefully and return accurate counts.
    """

    function_name = "count_doors"

    # Initialize the BAML ToolCreator
    try:
        tool_creator = ToolCreatorBAML(
            max_iterations=3,  # Keep low for testing
            log_level="INFO",
            path_ifc_model=TEST_IFC_PATH,
            add_code_prefix=True
        )
        print("✓ Successfully initialized BAML ToolCreator")
    except Exception as e:
        print(f"✗ Failed to initialize BAML ToolCreator: {e}")
        return False

    # Test the ToolCreator with comprehensive MLflow tracing
    try:
        print(f"\n🧪 Testing BAML ToolCreator for function: {function_name}")
        print(f"Requirements: {function_requirements[:100]}...")

        # Start MLflow run for comprehensive tracking
        start_time = time.time()

        with mlflow.start_run(run_name=f"ToolCreator_{function_name}") as run:
            # Log input parameters
            mlflow.log_param("function_name", function_name)
            mlflow.log_param("function_requirements", function_requirements[:200] + "..." if len(function_requirements) > 200 else function_requirements)
            mlflow.log_param("ifc_model_path", TEST_IFC_PATH)
            mlflow.log_param("max_iterations", 3)
            mlflow.log_param("log_level", "INFO")
            mlflow.log_param("add_code_prefix", True)
            mlflow.log_param("component_type", "BAML_ToolCreator")

            # Log additional configuration details
            mlflow.log_param("llm_provider", "Z.AI")
            mlflow.log_param("llm_model", "GLM-4.6")

            print(f"\n📊 MLflow run started: {run.info.run_id}")
            print(f"🔗 Tracking URI: {mlflow.get_tracking_uri()}")

            # Execute the ToolCreator with MLflow tracing
            result = tool_creator.forward(
                function_requirements=function_requirements,
                function_name=function_name,
                path_ifc_model=TEST_IFC_PATH,
            )

            execution_time = time.time() - start_time

            # Log execution metrics
            mlflow.log_metric("execution_time_seconds", execution_time)

            # Log results based on status
            if result.status == "success":
                if result.result and result.result.function_implementation:
                    # Success metrics
                    mlflow.log_metric("success_status", 1)
                    mlflow.log_metric("function_generated", 1)
                    mlflow.log_metric("function_length", len(result.result.function_implementation))

                    # Log the generated function
                    mlflow.log_param("generated_function", result.result.function_implementation)
                    mlflow.log_text(result.result.function_implementation, artifact_file=f"generated_function_{function_name}.py")

                    # Log LM metrics if available
                    if hasattr(result.result, 'lm_metrics') and result.result.lm_metrics:
                        lm_metrics = result.result.lm_metrics
                        if 'input_tokens' in lm_metrics:
                            mlflow.log_metric("input_tokens", lm_metrics['input_tokens'])
                        if 'output_tokens' in lm_metrics:
                            mlflow.log_metric("output_tokens", lm_metrics['output_tokens'])
                        if 'total_tokens' in lm_metrics:
                            mlflow.log_metric("total_tokens", lm_metrics['total_tokens'])
                        if 'lm_cost' in lm_metrics:
                            mlflow.log_metric("lm_cost", lm_metrics['lm_cost'])

                    # Log assessment status if available
                    if hasattr(result.result, 'assessment_status'):
                        mlflow.log_param("assessment_status", result.result.assessment_status)

                    print(f"\n📊 Result:")
                    print(f"Status: {result.status}")
                    print(f"⏱️  Execution time: {execution_time:.2f} seconds")
                    print("✓ Function implementation generated successfully!")
                    print(f"📝 Function length: {len(result.result.function_implementation)} characters")

                    print("\n🔧 Generated Function:")
                    print("-" * 50)
                    print(result.result.function_implementation)
                    print("-" * 50)

                    # Basic validation of the function
                    func_code = result.result.function_implementation
                    validation_passed = True
                    if f"def {function_name}" in func_code and "ifcopenshell" in func_code:
                        print("✓ Function contains expected name and IfcOpenShell import")
                        mlflow.log_metric("validation_passed", 1)
                    else:
                        print("⚠ Function may be missing expected name or IfcOpenShell import")
                        mlflow.log_metric("validation_passed", 0)
                        validation_passed = False

                    mlflow.log_metric("test_success", 1)
                    return True
                else:
                    print("✗ Success status but no function implementation found")
                    mlflow.log_metric("success_status", 1)
                    mlflow.log_metric("function_generated", 0)
                    mlflow.log_metric("test_success", 0)
                    mlflow.log_param("error_message", "Success status but no function implementation found")
                    return False
            else:
                print(f"✗ ToolCreator failed: {result.error_msg}")
                mlflow.log_metric("success_status", 0)
                mlflow.log_metric("function_generated", 0)
                mlflow.log_metric("test_success", 0)
                mlflow.log_param("error_message", result.error_msg or "Unknown error")
                return False

    except Exception as e:
        execution_time = time.time() - start_time if 'start_time' in locals() else 0
        print(f"✗ ToolCreator crashed: {str(e)}")

        # Log exception details if MLflow is available
        try:
            mlflow.log_metric("success_status", 0)
            mlflow.log_metric("test_success", 0)
            mlflow.log_metric("execution_time_seconds", execution_time)
            mlflow.log_param("error_message", str(e))
            mlflow.log_param("error_type", type(e).__name__)

            # Log full traceback
            import traceback
            error_traceback = traceback.format_exc()
            mlflow.log_text(error_traceback, artifact_file="error_traceback.txt")
        except:
            pass  # MLflow might not be available

        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing BAML ToolCreator Implementation")
    print("=" * 60)

    success = test_baml_tool_creator()

    print("\n" + "=" * 60)
    if success:
        print("🎉 BAML ToolCreator test completed successfully!")
    else:
        print("❌ BAML ToolCreator test failed!")

    sys.exit(0 if success else 1)