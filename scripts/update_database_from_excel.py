#!/usr/bin/env python3
"""
Script to update the experiment database with new data from Excel file.

This script:
1. Creates a clean database with only ifcmodels and ifc_bench tables
2. Deletes all existing data from these tables
3. Inserts new data from ifc-bench-v2.xlsx Excel file
4. Handles data type conversions (category: float64 -> INTEGER)

Usage:
    uv run python scripts/update_database_from_excel.py
"""

import sys
import os
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text, Column, Integer, Text, ForeignKey, CheckConstraint
from sqlmodel import SQLModel, Field, Session

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# Minimal models for clean database
class Ifcmodels(SQLModel, table=True):
    project_name: str = Field(sa_column=Column('project_name', Text, nullable=False))
    model_name: str = Field(sa_column=Column('model_name', Text, nullable=False))
    model_path: str = Field(sa_column=Column('model_path', Text, nullable=False))
    model_description: str = Field(sa_column=Column('model_description', Text, nullable=False))
    id: int = Field(default=None, sa_column=Column('id', Integer, primary_key=True))


class IfcBench(SQLModel, table=True):
    __tablename__ = 'ifc_bench'
    __table_args__ = (
        CheckConstraint('category BETWEEN 1 AND 4'),
    )

    question: str = Field(sa_column=Column('question', Text, nullable=False))
    ground_truth: str = Field(sa_column=Column('ground_truth', Text, nullable=False))
    ifc_id: int = Field(sa_column=Column('ifc_id', ForeignKey('ifcmodels.id'), nullable=False))
    id: int = Field(default=None, sa_column=Column('id', Integer, primary_key=True))
    category: int = Field(default=None, sa_column=Column('category', Integer))


def main():
    """Main function to update the database from Excel file."""

    # File paths
    excel_file = project_root / "src" / "experiment" / "db" / "ifc-bench-v2.xlsx"
    db_file = project_root / "src" / "experiment" / "db" / "db.db"

    print("=== Database Update from Excel ===")
    print(f"Excel file: {excel_file}")
    print(f"Database file: {db_file}")

    # Verify Excel file exists
    if not excel_file.exists():
        print(f"❌ Excel file not found: {excel_file}")
        return 1

    # Create database directory if needed
    if not db_file.parent.exists():
        print(f"📁 Creating database directory...")
        db_file.parent.mkdir(parents=True, exist_ok=True)

    # Create database engine
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url)

    # Create only the tables we need
    print("\n🔧 Creating clean database tables...")
    SQLModel.metadata.create_all(engine)
    print("   - Tables created successfully")

    try:
        # Read Excel data
        print("\n📖 Reading Excel file...")
        ifc_bench_df = pd.read_excel(excel_file, sheet_name='ifc-bench')
        ifcmodels_df = pd.read_excel(excel_file, sheet_name='ifcmodels')

        print(f"   - ifc-bench: {len(ifc_bench_df)} rows")
        print(f"   - ifcmodels: {len(ifcmodels_df)} rows")

        # Validate Excel structure
        expected_ifc_bench_cols = {'id', 'question', 'ground_truth', 'ifc_id', 'category'}
        expected_ifcmodels_cols = {'id', 'project_name', 'model_name', 'model_path', 'model_description'}

        if set(ifc_bench_df.columns) != expected_ifc_bench_cols:
            print(f"❌ Unexpected columns in ifc-bench sheet: {set(ifc_bench_df.columns)}")
            return 1

        if set(ifcmodels_df.columns) != expected_ifcmodels_cols:
            print(f"❌ Unexpected columns in ifcmodels sheet: {set(ifcmodels_df.columns)}")
            return 1

        # Process data
        print("\n🔄 Processing data...")

        # Handle category column conversion (float64 -> INTEGER, NaN -> NULL)
        ifc_bench_df['category'] = ifc_bench_df['category'].astype('Int64')  # Pandas nullable integer

        # Convert absolute paths to relative paths (remove everything before /src)
        print("   - Converting absolute paths to relative paths...")
        print("   - Sample path conversions:")
        for i, path in enumerate(ifcmodels_df['model_path'].head(3)):
            new_path = path.split('/src/', 1)[-1] if '/src/' in path else path
            new_path = 'src/' + new_path
            print(f"     {path} → {new_path}")

        ifcmodels_df['model_path'] = ifcmodels_df['model_path'].apply(
            lambda path: path.split('/src/', 1)[-1] if '/src/' in path else path
        )
        # Add 'src/' prefix back
        ifcmodels_df['model_path'] = 'src/' + ifcmodels_df['model_path']

        # Convert to records for database insertion
        ifc_bench_records = ifc_bench_df.to_dict('records')
        ifcmodels_records = ifcmodels_df.to_dict('records')

        # Database operations
        print("\n💾 Updating database...")

        with Session(engine) as session:
            # Clear existing data
            print("   - Clearing existing ifc_bench rows...")
            session.exec(text("DELETE FROM ifc_bench"))
            print("   - Clearing existing ifcmodels rows...")
            session.exec(text("DELETE FROM ifcmodels"))
            session.commit()

            # Insert new ifcmodels data using raw SQL
            print("   - Inserting new ifcmodels data...")
            for record in ifcmodels_records:
                insert_sql = text("""
                    INSERT INTO ifcmodels (id, project_name, model_name, model_path, model_description)
                    VALUES (:id, :project_name, :model_name, :model_path, :model_description)
                """)
                session.execute(insert_sql, record)
            session.commit()

            # Insert new ifc_bench data using raw SQL
            print("   - Inserting new ifc_bench data...")
            for record in ifc_bench_records:
                # Handle Int64 (nullable integer) conversion
                if pd.isna(record['category']):
                    record['category'] = None
                else:
                    record['category'] = int(record['category'])

                insert_sql = text("""
                    INSERT INTO ifc_bench (id, question, ground_truth, ifc_id, category)
                    VALUES (:id, :question, :ground_truth, :ifc_id, :category)
                """)
                session.execute(insert_sql, record)
            session.commit()

        # Verify results
        print("\n✅ Verifying results...")
        with Session(engine) as session:
            ifcmodels_count = session.exec(text("SELECT COUNT(*) FROM ifcmodels")).one()[0]
            ifc_bench_count = session.exec(text("SELECT COUNT(*) FROM ifc_bench")).one()[0]

            print(f"   - Ifcmodels: {ifcmodels_count} rows inserted")
            print(f"   - IFC-Bench: {ifc_bench_count} rows inserted")

            if ifcmodels_count == len(ifcmodels_records) and ifc_bench_count == len(ifc_bench_records):
                print("\n🎉 Database update completed successfully!")
                return 0
            else:
                print("\n❌ Database update failed - row count mismatch!")
                print(f"   Expected: Ifcmodels={len(ifcmodels_records)}, IFC-Bench={len(ifc_bench_records)}")
                print(f"   Actual: Ifcmodels={ifcmodels_count}, IFC-Bench={ifc_bench_count}")
                return 1

    except Exception as e:
        print(f"\n❌ Error during database update: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)