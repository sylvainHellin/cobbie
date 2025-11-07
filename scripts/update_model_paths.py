#!/usr/bin/env python3
"""
Script to update the model_path field in the ifcmodels table.
Replaces "experiment" with "db" in the path for each row.
"""

from sqlmodel import Session, select

from src.db import ENGINE
from src.db.models import Ifcmodels


def update_model_paths():
    """Update model_path field for all records in ifcmodels table."""

    with Session(ENGINE) as session:
        # Get all ifcmodels records
        statement = select(Ifcmodels)
        results = session.exec(statement)
        ifc_models = list(results)

        print(f"Found {len(ifc_models)} records to check")

        updated_count = 0

        for model in ifc_models:
            old_path = model.model_path

            # Replace "experiment" with "db" in the path
            if "experiment" in old_path:
                new_path = old_path.replace("experiment", "db")
                model.model_path = new_path

                print(f"Updated: {old_path} -> {new_path}")
                updated_count += 1
            else:
                print(f"No change needed: {old_path}")

        # Commit the changes to the database
        if updated_count > 0:
            session.commit()
            print(f"\nSuccessfully updated {updated_count} records")
        else:
            print("\nNo records needed updating")


if __name__ == "__main__":
    update_model_paths()