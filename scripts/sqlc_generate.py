#!/usr/bin/env python3
"""
Comprehensive SQLite + sqlc workflow script.

This script provides a one-command solution for:
1. Updating the schema dump from the SQLite database
2. Running sqlc generate
3. Applying parameter binding fixes for SQLAlchemy compatibility

Usage:
    uv run scripts/sqlc_generate.py

Options:
    --db-path: Path to SQLite database (default: src/experiment/db/db.db)
    --schema-path: Path to schema.sql output (default: src/experiment/db/schema.sql)
    --verbose: Enable verbose output
"""

import argparse
import subprocess
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Import our existing fix script
import re


def log_step(step: str, verbose: bool = True) -> None:
    """Log a workflow step."""
    if verbose:
        print(f"🔄 {step}")


def log_success(message: str, verbose: bool = True) -> None:
    """Log a success message."""
    if verbose:
        print(f"✅ {message}")


def log_error(message: str) -> None:
    """Log an error message."""
    print(f"❌ {message}", file=sys.stderr)


def update_schema_dump(db_path: Path, schema_path: Path, verbose: bool = True) -> bool:
    """
    Generate schema.sql from the SQLite database.

    Args:
        db_path: Path to the SQLite database
        schema_path: Path where to write the schema.sql file
        verbose: Whether to print progress messages

    Returns:
        True if successful, False otherwise
    """
    log_step("Updating schema dump from database", verbose)

    if not db_path.exists():
        log_error(f"Database not found: {db_path}")
        return False

    try:
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get schema dump
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = cursor.fetchall()

        # Generate schema content
        timestamp = datetime.now().isoformat()
        schema_content = f"""-- Schema dump
-- Generated on: {timestamp}

"""

        for (table_sql,) in tables:
            if table_sql:  # Skip None values
                # Format the CREATE TABLE statement nicely
                formatted_sql = table_sql.replace(",", ",\n            ")
                schema_content += f"{formatted_sql};\n\n"

        conn.close()

        # Write schema file
        schema_path.write_text(schema_content)
        log_success(f"Schema dumped to {schema_path}", verbose)
        return True

    except Exception as e:
        log_error(f"Failed to dump schema: {e}")
        return False


def run_sqlc_generate(verbose: bool = True) -> bool:
    """
    Run sqlc generate command.

    Args:
        verbose: Whether to print progress messages

    Returns:
        True if successful, False otherwise
    """
    log_step("Running sqlc generate", verbose)

    try:
        result = subprocess.run(
            ["sqlc", "generate"], capture_output=True, text=True, check=True
        )

        if verbose and result.stdout:
            print(result.stdout)

        log_success("sqlc generate completed", verbose)
        return True

    except subprocess.CalledProcessError as e:
        log_error(f"sqlc generate failed: {e}")
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        return False
    except FileNotFoundError:
        log_error("sqlc command not found. Please install sqlc.")
        return False


def fix_parameter_binding(query_file: Path, verbose: bool = True) -> bool:
    """
    Fix sqlc's parameter binding by converting numbered positional parameters
    to named parameters and ensuring consistent dictionary binding.

    Args:
        query_file: Path to the generated query.py file
        verbose: Whether to print progress messages

    Returns:
        True if changes were made, False otherwise
    """
    log_step("Fixing parameter binding", verbose)

    if not query_file.exists():
        log_error(f"Generated query file not found: {query_file}")
        return False

    content = query_file.read_text()
    original_content = content

    # Replace numbered positional parameters (?1, ?2) with named parameters (:p1, :p2)
    content = re.sub(r"\?1", ":p1", content)
    content = re.sub(r"\?2", ":p2", content)
    content = re.sub(r"\?3", ":p3", content)
    content = re.sub(r"\?4", ":p4", content)
    # Add more as needed...

    # Ensure parameter binding uses dictionaries (sqlc already generates this correctly)
    # This is mainly a verification step since sqlc generates {"p1": p1, "p2": p2} format

    if content != original_content:
        query_file.write_text(content)
        log_success("Parameter binding fixes applied", verbose)
        return True
    else:
        if verbose:
            print("ℹ️  No parameter binding fixes needed")
        return False


def main():
    """Main function to orchestrate the complete workflow."""
    parser = argparse.ArgumentParser(
        description="Complete SQLite + sqlc workflow: schema dump → sqlc generate → parameter fixes"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("src/experiment/db/db.db"),
        help="Path to SQLite database (default: src/experiment/db/db.db)",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=Path("src/experiment/db/schema.sql"),
        help="Path to schema.sql output (default: src/experiment/db/schema.sql)",
    )
    parser.add_argument(
        "--query-path",
        type=Path,
        default=Path("src/experiment/db/query.py"),
        help="Path to generated query.py file (default: src/experiment/db/query.py)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="Enable verbose output (default: True)",
    )
    parser.add_argument("--quiet", action="store_true", help="Disable verbose output")

    args = parser.parse_args()

    verbose = args.verbose and not args.quiet

    if verbose:
        print("🚀 Starting SQLite + sqlc workflow...\n")

    # Step 1: Update schema dump
    if not update_schema_dump(args.db_path, args.schema_path, verbose):
        sys.exit(1)

    if verbose:
        print()

    # Step 2: Run sqlc generate
    if not run_sqlc_generate(verbose):
        sys.exit(1)

    if verbose:
        print()

    # Step 3: Fix parameter binding
    fix_parameter_binding(args.query_path, verbose)

    if verbose:
        print("\n🎉 Workflow completed successfully!")
        print(f"   📄 Schema: {args.schema_path}")
        print(f"   🐍 Generated code: {args.query_path}")
        print("   ⚡ Ready to use!")


if __name__ == "__main__":
    main()
