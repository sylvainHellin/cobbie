"""Database population script for initial data loading."""

import os
import pandas as pd

try:
    # Try relative imports first (when imported as module)
    from .create_db import init_sqlite_db, drop_and_recreate_tables
    from .models import IfcModelRow, DatasetRow
    from .update_db import insert_new_ifc_model, insert_new_dataset_row
    from .query_db import get_ifc_models
except ImportError:
    # Fall back to absolute imports (when run as script)
    from src.experiment.db.create_db import init_sqlite_db, drop_and_recreate_tables
    from src.experiment.db.models import IfcModelRow, DatasetRow
    from src.experiment.db.update_db import insert_new_ifc_model, insert_new_dataset_row
    from src.experiment.db.query_db import get_ifc_models


def populate_database():
    """Populate the database with initial data from CSV files."""
    try:
        from src.config import (
            DATASET_PATH,
            CSV_IFC_MODELS_PATH,
            DIRECTORY_IFC_MODELS_PATH,
        )
    except ImportError:
        print(
            "Warning: Could not import config. Make sure you're running from the correct directory."
        )
        return

    # Initialize the database
    init_sqlite_db()
    print("DB initialized successfully\n")

    # Drop and recreate all tables to ensure a clean slate
    drop_and_recreate_tables()
    print("Tables dropped and recreated successfully\n")

    # Populate IFC models table
    print("Populating IFC models...")
    ifc_models_df = pd.read_csv(filepath_or_buffer=CSV_IFC_MODELS_PATH)
    for row in ifc_models_df.itertuples(name="ifc_models"):
        ifc_model = IfcModelRow(
            project_name=row.project_name,  # type: ignore
            model_name=row.model_name,  # type: ignore
            model_path=os.path.join(
                DIRECTORY_IFC_MODELS_PATH,
                row.project_name,  # type: ignore
                f"{row.model_name}.ifc",  # type: ignore
            ),
            model_description=row.model_description,  # type: ignore
        )
        model_id = insert_new_ifc_model(ifc_model=ifc_model)
        print(
            f"  Inserted IFC model: {row.project_name}/{row.model_name} (ID: {model_id})"  # type: ignore
        )

    # Populate Dataset table
    print("\nPopulating dataset...")
    dataset_df = pd.read_csv(filepath_or_buffer=DATASET_PATH)
    for row in dataset_df.itertuples(name="dataset"):
        ifc_models_list = get_ifc_models(
            project_name=row.project,  # type: ignore
            model_name=row.ifc_model,  # type: ignore
        )

        if not ifc_models_list:
            print(
                f"  Warning: Could not find a corresponding model for project: "
                f"{row.project} and model: {row.ifc_model}"  # type: ignore
            )
            continue

        for model in ifc_models_list:
            if model.id is None:
                print(
                    f"  Warning: Model found but has no ID for project: "
                    f"{row.project} and model: {row.ifc_model}"  # type: ignore
                )
                continue

            new_row = DatasetRow(
                question=row.question,  # type: ignore
                answer=row.answer,  # type: ignore
                ifc_id=model.id,
            )

            dataset_id = insert_new_dataset_row(dataset=new_row)
            print(
                f"  Inserted dataset row: Question ID {dataset_id} for IFC model {model.id}"
            )

    print("\nDatabase population completed successfully!")


def main():
    """Main function to run the database population."""
    populate_database()


if __name__ == "__main__":
    main()
