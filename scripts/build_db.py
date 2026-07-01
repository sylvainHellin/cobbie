#!/usr/bin/env python
"""
build_db.py — Build the Cobbie SQLite database (src/db/db.db) from the
IFC-Bench dataset.

The IFC-Bench dataset on HuggingFace ships question-answer pairs as a CSV
plus per-project IFC model folders, but Cobbie expects a prebuilt SQLite
database at src/db/db.db. This script creates that database: it sets up the
schema, loads the QA pairs, registers the IFC models referenced by the
questions, fills in model descriptions from each project's model_card.md,
and verifies the result.

Per the README, the IFC model folders are expected under src/db/bim_models/.
The questions CSV is not stored in the repo; pass its path with --csv.

Usage (from the repo root):

    uv run python scripts/build_db.py --csv /path/to/ifc-bench-v2.csv

ROOT_PATH is read from the project's .env file (the same one Cobbie uses),
and can be overridden on the command line, e.g.
``ROOT_PATH=/path uv run python scripts/build_db.py --csv ...``.

Options:
    --csv  Path to the downloaded ifc-bench-v2.csv (required)
    --db   Output database path (default: src/db/db.db)
"""
import argparse
import os
import re
import sqlite3
import sys

import pandas as pd
from dotenv import find_dotenv, load_dotenv

# Load .env the same way src/config.py does, so ROOT_PATH (and anything else)
# comes from the project's .env file without needing to be set on the command line.
load_dotenv(find_dotenv())


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ifcmodels (
    id                INTEGER PRIMARY KEY,
    project_name      TEXT NOT NULL,
    model_name        TEXT NOT NULL,
    model_path        TEXT NOT NULL,
    model_description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ifc_bench (
    id           INTEGER PRIMARY KEY,
    question     TEXT NOT NULL,
    ground_truth TEXT NOT NULL,
    ifc_id       INTEGER NOT NULL REFERENCES ifcmodels(id),
    category     INTEGER CHECK (category BETWEEN 1 AND 4),
    cobbie       TEXT
);

CREATE TABLE IF NOT EXISTS tool_usage_stats (
    tool_name                      TEXT PRIMARY KEY,
    questions_when_included        INTEGER DEFAULT 0,
    questions_when_called          INTEGER DEFAULT 0,
    questions_correct_contribution INTEGER DEFAULT 0,
    questions_wrong_contribution   INTEGER DEFAULT 0,
    created_at_question            INTEGER DEFAULT 0,
    last_question_processed        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tool_usage_stats_eval (
    tool_name                      TEXT PRIMARY KEY,
    questions_when_included        INTEGER NOT NULL DEFAULT 0,
    questions_when_called          INTEGER NOT NULL DEFAULT 0,
    questions_correct_contribution INTEGER NOT NULL DEFAULT 0,
    questions_wrong_contribution   INTEGER NOT NULL DEFAULT 0
);
"""

# Expected category distribution for the v2 dataset (sanity check only).
EXPECTED = {1: 152, 2: 568, 3: 112, 4: 194}

# model_path values are stored relative to the repo root, matching the
# convention used by the published db.db (e.g. src/db/bim_models/duplex/arc.ifc).
MODELS_REL_PREFIX = "src/db/bim_models"


def model_description(bim_dir, project, ifc_model):
    """Return a per-model description from the project's model_card.md.

    Tries the per-file table row first, then the project-level
    ``## Description`` section, then a generated placeholder.
    """
    card = os.path.join(bim_dir, str(project), "model_card.md")
    target = f"{ifc_model}.ifc"
    try:
        with open(card, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return f"{ifc_model} model for project {project}"

    # 1) per-file table row:  | `arc.ifc` | Architecture | <description> |
    for line in text.splitlines():
        if line.strip().startswith("|") and target in line:
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0] == target:
                return cells[2]

    # 2) fall back to the project-level "## Description" section
    m = re.search(r"##\s*Description\s*\n+(.+)", text)
    if m:
        return m.group(1).strip()

    # 3) last resort
    return f"{ifc_model} model for project {project}"


def build(csv_path, bim_dir, db_path):
    """Create the schema and load the dataset into a fresh database.

    ``bim_dir`` is the absolute directory the IFC files live in (used to read
    model_card.md and verify files); the stored ``model_path`` is repo-root
    relative so it matches the published db.db.
    """
    df = pd.read_csv(csv_path)

    # The CSV carries a stable identity via an explicit ``id`` column; consume it
    # directly so the db id equals the CSV id regardless of row order.
    if "id" not in df.columns:
        raise SystemExit(
            "CSV is missing the required 'id' column. Expected a leading 'id' "
            "column (1..N) that pins each question's stable identity."
        )
    if df["id"].duplicated().any():
        raise SystemExit("CSV 'id' column contains duplicate values; ids must be unique.")

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.executescript(SCHEMA)

    # Clean so re-runs don't duplicate rows.
    cur.execute("DELETE FROM ifc_bench")
    cur.execute("DELETE FROM ifcmodels")

    # ifcmodels: one row per unique (project, ifc_model) referenced by the CSV.
    # model_path is stored relative to the repo root (src/db/bim_models/...),
    # matching the published db.db; the code resolves it from ROOT_PATH at runtime.
    model_id = {}
    for (project, ifc_model), _ in df.groupby(["project", "ifc_model"]):
        rel_path = os.path.join(MODELS_REL_PREFIX, str(project), f"{ifc_model}.ifc")
        cur.execute(
            "INSERT INTO ifcmodels "
            "(project_name, model_name, model_path, model_description) "
            "VALUES (?, ?, ?, ?)",
            (str(project), str(ifc_model), rel_path,
             model_description(bim_dir, project, ifc_model)),
        )
        model_id[(project, ifc_model)] = cur.lastrowid

    # ifc_bench: the QA pairs, each linked to its IFC model. The explicit ``id``
    # from the CSV is inserted as the primary key so the db id == CSV id and is
    # robust to any future row reordering (instead of relying on iterrows order).
    for _, r in df.iterrows():
        cur.execute(
            "INSERT INTO ifc_bench "
            "(id, question, ground_truth, ifc_id, category, cobbie) "
            "VALUES (?, ?, ?, ?, ?, NULL)",
            (int(r["id"]), r["question"], r["ground_truth"],
             model_id[(r["project"], r["ifc_model"])], int(r["category"])),
        )

    con.commit()
    return con, cur


def report(cur, bim_dir, root):
    """Print counts, verify the category split, and check files on disk.

    Stored model_path values are repo-root relative, so they are resolved
    against ``root`` before checking the filesystem.
    """
    n_models = cur.execute("SELECT COUNT(*) FROM ifcmodels").fetchone()[0]
    n_q = cur.execute("SELECT COUNT(*) FROM ifc_bench").fetchone()[0]
    print(f"Inserted {n_models} models and {n_q} questions.")

    print("By category:")
    counts = dict(cur.execute(
        "SELECT category, COUNT(*) FROM ifc_bench GROUP BY category ORDER BY category"
    ))
    ok = True
    for cat in sorted(EXPECTED):
        got = counts.get(cat, 0)
        flag = "" if got == EXPECTED[cat] else f"  <-- expected {EXPECTED[cat]}"
        ok = ok and got == EXPECTED[cat]
        print(f"   {cat}: {got}{flag}")
    if ok:
        print("Category counts match the v2 dataset. \u2713")

    missing = [p for (p,) in cur.execute("SELECT model_path FROM ifcmodels")
               if not os.path.exists(os.path.join(root, p))]
    if missing:
        print(f"\n\u26a0\ufe0f  {len(missing)} model file(s) not found on disk, e.g.:")
        for p in missing[:5]:
            print("   ", p)
        print(f"   \u2192 copy the dataset's projects/* into {bim_dir}")
    else:
        print("All model files found on disk. \u2713")


def main():
    root = os.environ.get("ROOT_PATH", os.getcwd())
    ap = argparse.ArgumentParser(
        description="Build the Cobbie SQLite database from the IFC-Bench CSV."
    )
    ap.add_argument("--csv", default=None,
                    help="path to the downloaded ifc-bench-v2.csv (required)")
    ap.add_argument("--db", default="src/db/db.db",
                    help="output database path")
    args = ap.parse_args()

    bim_dir = os.path.join(root, "src/db/bim_models")

    if not args.csv or not os.path.exists(args.csv):
        location = args.csv if args.csv else "(none given)"
        sys.exit(
            f"Questions CSV not found: {location}\n\n"
            "The CSV is not stored in this repo. Point --csv at your downloaded\n"
            "ifc-bench-v2.csv from the IFC-Bench dataset on HuggingFace, e.g.:\n\n"
            "    uv run python scripts/build_db.py --csv /path/to/ifc-bench-v2.csv\n"
        )

    con, cur = build(args.csv, bim_dir, args.db)
    report(cur, bim_dir, root)
    con.close()
    print(f"\nDatabase written to {args.db}")


if __name__ == "__main__":
    main()
