#!/usr/bin/env python3
"""
Test script for BAML TestAndImprove components.
Tests individual workflows to ensure proper functionality.
"""

import os
import sys
from dotenv import load_dotenv

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.config.main import TEST_IFC_PATH
from src.engine.components.test_and_improve_baml import TestAndImproveBAML
from src.engine.util import _create_function_from_source_code
from src.engine.tools.primordial import web_search, query_ifcopenshell_documentation
from baml_client.types import TestAndImproveSuccess, TestAndImproveError


def test_code_cleaner():
    """Test the BAML CodeCleaner component."""
    print("🧪 Testing BAML CodeCleaner...")

    from baml_client import b
    from src.engine.util.baml_common import run_baml_function_with_metrics

    # Test data with syntax error
    faulty_code = '''
def count_doors(ifc_file_path: str) -> int:
    """Count all doors in an IFC model."""
    model = ifcopenshell.open(ifc_file_path)  # Missing import
    doors = model.by_type("IfcDoor"  # Missing closing parenthesis
    return str(len(doors))
'''
    error_msg = "'(' was never closed (<string>, line 4)"

    try:
        result, collector = run_baml_function_with_metrics(
            "CodeCleaner",
            b.CodeCleaner,
            faulty_code=faulty_code,
            error_message=error_msg
        )

        print(f"✅ CodeCleaner test passed")
        print(f"   Result type: {type(result).__name__}")
        print(f"   Success: {result.success if hasattr(result, 'success') else 'Unknown'}")
        if hasattr(result, 'reasoning'):
            print(f"   Reasoning: {result.reasoning[:100]}...")
        return True

    except Exception as e:
        print(f"❌ CodeCleaner test failed: {str(e)}")
        return False


def test_tool_assessor():
    """Test the BAML ToolAssessor component through TestAndImproveBAML."""
    print("\n🧪 Testing BAML ToolAssessor through TestAndImproveBAML...")

    from src.engine.components.test_and_improve_baml import TestAndImproveBAML

    # Test function implementation (with wrong return type)
    function_implementation = '''
import ifcopenshell
def count_doors(ifc_file_path: str) -> int:
    """Count all doors in an IFC model."""
    model = ifcopenshell.open(ifc_file_path)
    doors = model.by_type("IfcDoor")
    return str(len(doors))  # Wrong return type
'''

    function_requirements = "Count all doors in an IFC model and return as integer"
    function_name = "count_doors"

    try:
        # Initialize TestAndImproveBAML with max_iterations=1 to test just the assessment
        test_and_improve = TestAndImproveBAML(max_iterations=1)

        # Add the function to the interpreter
        creation_result = _create_function_from_source_code(
            function_name=function_name,
            code=function_implementation
        )

        if creation_result.is_err():
            print(f"❌ Failed to create test function: {creation_result.unwrap_err()}")
            return False

        test_function = creation_result.unwrap()
        test_and_improve.add_function_to_interpreter(function_name, test_function)

        # Setup function and assessor config first
        test_and_improve.iter = 0
        assessor_config, setup_success = test_and_improve._create_function_and_setup_assessor(
            function_name=function_name,
            function_implementation=function_implementation
        )

        if not setup_success:
            print(f"❌ Failed to setup assessor")
            return False

        # Run the assessment phase
        assessment_result, success = test_and_improve._perform_assessment(
            function_name=function_name,
            function_requirements=function_requirements,
            path_ifc_model=TEST_IFC_PATH,
            assessor_config=assessor_config
        )

        print(f"✅ ToolAssessor test completed")
        print(f"   Success: {success}")

        if success and assessment_result and assessment_result.assessment_status:
            print(f"   Assessment Status: {assessment_result.assessment_status}")
            print(f"   Assessment Details: {assessment_result.assessment_details[:150]}...")

        return success and assessment_result is not None

    except Exception as e:
        print(f"❌ ToolAssessor test failed: {str(e)}")
        return False


def test_tool_corrector():
    """Test the BAML ToolCorrector component through TestAndImproveBAML."""
    print("\n🧪 Testing BAML ToolCorrector through TestAndImproveBAML...")

    from src.engine.components.test_and_improve_baml import TestAndImproveBAML

    # Test function implementation (with wrong return type)
    current_implementation = '''
import ifcopenshell
def count_doors(ifc_file_path: str) -> int:
    """Count all doors in an IFC model."""
    model = ifcopenshell.open(ifc_file_path)
    doors = model.by_type("IfcDoor")
    return str(len(doors))  # Wrong return type
'''

    function_requirements = "Count all doors in an IFC model and return as integer"
    function_name = "count_doors"
    assessment_feedback = "The function correctly counts doors but returns a string instead of an integer, violating the requirement that it should return an integer type."

    try:
        # Initialize TestAndImproveBAML
        test_and_improve = TestAndImproveBAML(max_iterations=1)

        # Add the original function to the interpreter
        creation_result = _create_function_from_source_code(
            function_name=function_name,
            code=current_implementation
        )

        if creation_result.is_err():
            print(f"❌ Failed to create test function: {creation_result.unwrap_err()}")
            return False

        test_function = creation_result.unwrap()
        test_and_improve.add_function_to_interpreter(function_name, test_function)

        # Run the correction phase
        test_and_improve.iter = 0
        improved_implementation, success = test_and_improve._perform_correction(
            function_requirements=function_requirements,
            function_name=function_name,
            current_function_implementation=current_implementation,
            detailed_assessment=assessment_feedback,
            path_ifc_model=TEST_IFC_PATH
        )

        print(f"✅ ToolCorrector test completed")
        print(f"   Success: {success}")

        if success and improved_implementation:
            print(f"   ✅ Function successfully improved")
            print(f"   Improved implementation length: {len(improved_implementation)} chars")
        else:
            print(f"   ⚠️  Function improvement incomplete")

        return success and improved_implementation is not None

    except Exception as e:
        print(f"❌ ToolCorrector test failed: {str(e)}")
        return False


def test_full_test_and_improve():
    """Test the complete TestAndImproveBAML workflow."""
    print("\n🧪 Testing complete TestAndImproveBAML workflow...")

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

    # Faulty implementation that should be improved
    function_implementation = '''
import ifcopenshell
def count_doors(ifc_file_path: str) -> int:
    """Count all doors in an IFC model."""
    model = ifcopenshell.open(ifc_file_path)
    doors = model.by_type("IfcDoor")
    return str(len(doors))  # Wrong return type - should be int
'''

    try:
        test_and_improve = TestAndImproveBAML(
            max_iterations=2,
            log_level="INFO"
        )

        result = test_and_improve.forward(
            function_requirements=function_requirements,
            function_name=function_name,
            path_ifc_model=TEST_IFC_PATH,
            function_implementation=function_implementation
        )

        print(f"✅ Full TestAndImproveBAML test completed")

        if isinstance(result, TestAndImproveSuccess):
            print(f"   Status: SUCCESS")
            print(f"   ✅ Function successfully improved")
            print(f"   Final implementation length: {len(result.function_implementation)} chars")
            print(f"   Iterations Used: {result.iterations_used}")
            print(f"   Total Time: {result.total_time_seconds:.2f} seconds")
            return True
        elif isinstance(result, TestAndImproveError):
            print(f"   Status: ERROR")
            print(f"   Error Message: {result.error_message}")
            print(f"   ⚠️  Function improvement incomplete")
            print(f"   Iterations Completed: {result.iterations_completed}")
            return False
        else:
            print(f"   Status: UNKNOWN")
            print(f"   Unknown result type: {type(result)}")
            return False

    except Exception as e:
        print(f"❌ Full TestAndImproveBAML test failed: {str(e)}")
        return False


def main():
    """Run all tests."""
    print("🚀 Starting BAML TestAndImprove component tests\n")

    # Load environment variables
    load_dotenv()

    # Setup MLflow experiment and run
    import mlflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("BAML_TestAndImprove_Migration_Test")

    with mlflow.start_run(run_name="BAML_TestAndImprove_Component_Tests") as run:
        print(f"📊 MLflow Run: {run.info.run_id}")
        print(f"🔗 MLflow UI: http://127.0.0.1:5000/#/experiments/{run.info.experiment_id}/runs/{run.info.run_id}\n")

        # Log experiment parameters
        mlflow.log_params({
            "test_type": "BAML_TestAndImprove_Migration",
            "components_tested": ["CodeCleaner", "ToolAssessor", "ToolCorrector", "FullWorkflow"],
            "test_file": "test/test_and_improve_baml_test.py",
            "baml_schema": "baml_src/test_and_improve.baml",
            "implementation": "src/engine/components/test_and_improve_baml.py"
        })

        # Run individual component tests
        tests = [
            ("CodeCleaner", test_code_cleaner),
            ("ToolAssessor", test_tool_assessor),
            ("ToolCorrector", test_tool_corrector),
            ("Full Workflow", test_full_test_and_improve)
        ]

        results = []
        test_metrics = {}

        for test_name, test_func in tests:
            print(f"\n{'='*20} {test_name} {'='*20}")
            try:
                result = test_func()
                results.append((test_name, result))
                test_metrics[f"{test_name.lower()}_passed"] = 1 if result else 0
                print(f"✅ {test_name} completed: {'PASSED' if result else 'FAILED'}")
            except Exception as e:
                print(f"❌ {test_name} test crashed: {str(e)}")
                results.append((test_name, False))
                test_metrics[f"{test_name.lower()}_passed"] = 0
                test_metrics[f"{test_name.lower()}_error"] = str(e)
                # Log error as artifact
                mlflow.log_text(str(e), artifact_file=f"{test_name.lower()}_error.txt")

        # Log test metrics to MLflow
        mlflow.log_metrics(test_metrics)

        # Summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)

        passed = 0
        summary_data = []

        for test_name, result in results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{test_name:<20} {status}")
            summary_data.append({
                "test_name": test_name,
                "status": "PASSED" if result else "FAILED",
                "passed": 1 if result else 0
            })
            if result:
                passed += 1

        success_rate = (passed / len(results)) * 100
        print(f"\nOverall: {passed}/{len(results)} tests passed ({success_rate:.1f}%)")

        # Log final summary to MLflow
        mlflow.log_metrics({
            "total_tests": len(results),
            "tests_passed": passed,
            "tests_failed": len(results) - passed,
            "success_rate": success_rate
        })

        # Log summary as artifact
        import json
        mlflow.log_text(json.dumps(summary_data, indent=2), artifact_file="test_summary.json")

        if passed == len(results):
            print("🎉 All tests passed! BAML TestAndImprove migration successful.")
            mlflow.set_tag("test_result", "SUCCESS")
            return 0
        else:
            print("⚠️  Some tests failed. Check the logs above for details.")
            mlflow.set_tag("test_result", "PARTIAL_SUCCESS")
            return 1


if __name__ == "__main__":
    exit(main())