#!/usr/bin/env python3
"""
Script to import questions from Excel file into the experiment database.
Maps project_name and model_name to ifc_id using the ifcmodels table.
"""

import sqlite3
import pandas as pd
import sys
from pathlib import Path


def import_excel_to_db(excel_path: str, db_path: str) -> None:
    """
    Import questions from Excel file to database with proper ifc_id lookup.

    Args:
        excel_path: Path to the Excel file
        db_path: Path to the SQLite database
    """
    # Validate paths
    excel_file = Path(excel_path)
    db_file = Path(db_path)

    if not excel_file.exists():
        print(f"Error: Excel file not found: {excel_path}")
        sys.exit(1)

    if not db_file.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    print(f"Reading Excel file: {excel_path}")

    # Read Excel file, skip first row (headers)
    try:
        df = pd.read_excel(excel_path)
        print(f"Found {len(df)} rows in Excel file")
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        sys.exit(1)

    # Clean and filter columns - keep only the ones we need
    required_columns = ['question', 'ground_truth', 'model_name', 'project_name', 'category']
    available_columns = [col for col in required_columns if col in df.columns]

    if len(available_columns) != len(required_columns):
        print(f"Error: Missing required columns. Available: {available_columns}")
        sys.exit(1)

    # Filter to only required columns and drop rows with missing critical data
    df_clean = df[required_columns].copy()
    df_clean = df_clean.dropna(subset=['question', 'ground_truth', 'project_name'])

    print(f"After cleaning: {len(df_clean)} valid rows")

    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

    # Get all ifc models for lookup
    print("Loading IFC models from database...")
    cursor.execute("SELECT id, project_name, model_name FROM ifcmodels")
    ifc_models = cursor.fetchall()

    # Create lookup dictionary: (project_name, model_name) -> id
    ifc_lookup = {}
    for ifc_id, project_name, model_name in ifc_models:
        key = (project_name.lower().strip(), model_name.lower().strip() if pd.notna(model_name) else None)
        ifc_lookup[key] = ifc_id

    print(f"Loaded {len(ifc_models)} IFC models from database")

    # Process each row and prepare for insertion
    successful_imports = 0
    failed_lookups = []

    for idx, row in df_clean.iterrows():
        project_name = str(row['project_name']).strip()
        model_name = str(row['model_name']).strip() if pd.notna(row['model_name']) else None

        # Try different lookup strategies
        ifc_id = None

        # Strategy 1: Exact match with model_name
        if model_name and model_name != 'nan':
            key = (project_name.lower(), model_name.lower())
            ifc_id = ifc_lookup.get(key)

        # Strategy 2: Try with None model_name (if model_name was empty in Excel)
        if ifc_id is None:
            key = (project_name.lower(), None)
            ifc_id = ifc_lookup.get(key)

        # Strategy 3: Try partial matching for project_name
        if ifc_id is None:
            for (db_project, db_model), id in ifc_lookup.items():
                if project_name.lower() in db_project or db_project in project_name.lower():
                    if model_name and model_name != 'nan' and db_model and model_name.lower() in db_model:
                        ifc_id = id
                        break
                    elif not model_name or model_name == 'nan':
                        ifc_id = id
                        break

        if ifc_id is None:
            failed_lookups.append((idx + 2, project_name, model_name))  # +2 because Excel is 1-indexed and we have header
            continue

        # Handle category - convert to integer, set to 1 if NaN/invalid
        try:
            category = int(row['category']) if pd.notna(row['category']) else 1
            if category < 1 or category > 4:
                category = 1
        except (ValueError, TypeError):
            category = 1

        # Insert into database
        try:
            cursor.execute(
                """
                INSERT INTO dataset (question, ground_truth, ifc_id, category)
                VALUES (?, ?, ?, ?)
                """,
                (row['question'], row['ground_truth'], ifc_id, category)
            )
            successful_imports += 1
        except Exception as e:
            print(f"Error inserting row {idx + 2}: {e}")
            failed_lookups.append((idx + 2, project_name, model_name, f"DB Error: {e}"))

    # Commit changes
    conn.commit()
    conn.close()

    # Report results
    print(f"\nImport completed!")
    print(f"Successfully imported: {successful_imports} rows")
    print(f"Failed lookups: {len(failed_lookups)} rows")

    if failed_lookups:
        print("\nFailed rows (Excel row number, project_name, model_name):")
        for failed_row in failed_lookups[:10]:  # Show first 10 only
            if len(failed_row) == 4:
                print(f"  Row {failed_row[0]}: {failed_row[1]} / {failed_row[2]} - {failed_row[3]}")
            else:
                print(f"  Row {failed_row[0]}: {failed_row[1]} / {failed_row[2]}")

        if len(failed_lookups) > 10:
            print(f"  ... and {len(failed_lookups) - 10} more")


if __name__ == "__main__":
    # Default paths based on the project structure
    excel_path = "src/experiment/datasets/ifc-bench-250929.xlsx"
    db_path = "src/experiment/db/db.db"

    # Allow command line arguments to override paths
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    if len(sys.argv) > 2:
        db_path = sys.argv[2]

    import_excel_to_db(excel_path, db_path)