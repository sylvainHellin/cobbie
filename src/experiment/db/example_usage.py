"""Example usage of the modular database structure."""

import os
from datetime import datetime

# Import specific functions from the modular database structure
from src.experiment.db import (
    # Database creation
    init_sqlite_db,
    drop_and_recreate_tables,
    # Models
    IfcModelRow,
    DatasetRow,
    RunsRow,
    LogRow,
    # Query functions
    get_ifc_models,
    get_dataset_row,
    get_run_row,
    # Update functions
    insert_new_ifc_model,
    insert_new_dataset_row,
    insert_new_run,
    insert_new_log,
    # Population function
    populate_database,
)


def example_create_and_query():
    """Example of creating database and querying data."""
    print("=== Database Creation Example ===")

    # Initialize database
    init_sqlite_db()
    print("✓ Database initialized")

    # Create a new IFC model
    new_model = IfcModelRow(
        project_name="example_project",
        model_name="example_model",
        model_path="/path/to/example.ifc",
        model_description="An example IFC model for testing",
    )

    model_id = insert_new_ifc_model(new_model)
    print(f"✓ Inserted IFC model with ID: {model_id}")

    # Create a dataset entry
    dataset_entry = DatasetRow(
        question="What is the total floor area?",
        answer="250 square meters",
        ifc_id=model_id,
    )

    dataset_id = insert_new_dataset_row(dataset_entry)
    print(f"✓ Inserted dataset row with ID: {dataset_id}")


def example_query_data():
    """Example of querying existing data."""
    print("\n=== Data Query Example ===")

    # Get all IFC models
    all_models = get_ifc_models()
    print(f"✓ Found {len(all_models)} IFC models")

    for model in all_models[:3]:  # Show first 3 models
        print(f"  - {model.project_name}/{model.model_name} (ID: {model.id})")

    # Get a specific dataset row
    if all_models:
        # Find a dataset row for the first model
        first_model_id = all_models[0].id
        dataset_row = get_dataset_row(1)  # Get first dataset row
        if dataset_row.question:
            print(f"✓ Sample question: {dataset_row.question[:50]}...")


def example_run_tracking():
    """Example of tracking a run with logs."""
    print("\n=== Run Tracking Example ===")

    # Create a new run
    new_run = RunsRow(
        question_id=1,
        llm="gpt-4",
        input_tokens=150,
        output_tokens=75,
        duration=2.5,
        timestamp=datetime.now(),
    )

    run_id = insert_new_run(new_run)
    print(f"✓ Created run with ID: {run_id}")

    # Add some logs to the run
    log_entries = [
        LogRow(
            run_id=run_id,
            agent_name="query_agent",
            step_number=1,
            timestamp=datetime.now(),
            model_output="Analyzing IFC model structure...",
            action_input_code="ifc_parser.get_elements('IfcWall')",
            action_output="Found 24 wall elements",
            observations="Wall elements successfully identified",
            duration=0.8,
            input_tokens=50,
            output_tokens=25,
        ),
        LogRow(
            run_id=run_id,
            agent_name="calculation_agent",
            step_number=2,
            timestamp=datetime.now(),
            model_output="Calculating total area...",
            action_input_code="sum(wall.area for wall in walls)",
            action_output="Total area: 250 m²",
            observations="Area calculation completed",
            duration=0.3,
            input_tokens=30,
            output_tokens=15,
        ),
    ]

    for log_entry in log_entries:
        log_id = insert_new_log(log_entry)
        print(f"✓ Added log entry with ID: {log_id}")


def example_search_and_filter():
    """Example of searching and filtering data."""
    print("\n=== Search and Filter Example ===")

    # Search for specific project models
    duplex_models = get_ifc_models(project_name="duplex")
    print(f"✓ Found {len(duplex_models)} models in 'duplex' project")

    # Search for specific model type
    arc_models = get_ifc_models(model_name="arc")
    print(f"✓ Found {len(arc_models)} 'arc' models across all projects")

    # Search with multiple criteria
    specific_model = get_ifc_models(project_name="duplex", model_name="arc")
    if specific_model:
        model = specific_model[0]
        print(f"✓ Found specific model: {model.project_name}/{model.model_name}")
        print(f"  Path: {model.model_path}")
        print(f"  Description: {model.model_description}")


def main():
    """Main function demonstrating the modular database usage."""
    print("🏗️  Database Module Usage Examples")
    print("=" * 50)

    try:
        # Run examples
        example_create_and_query()
        example_query_data()
        example_run_tracking()
        example_search_and_filter()

        print("\n✅ All examples completed successfully!")
        print("\n📚 Available modules:")
        print("  • create_db.py - Database initialization and schema")
        print("  • models.py - Data models and utilities")
        print("  • query_db.py - Database query functions")
        print("  • update_db.py - Database insert/update functions")
        print("  • populate_db.py - Initial data population")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        print("Make sure the database is properly configured and accessible.")


if __name__ == "__main__":
    main()
