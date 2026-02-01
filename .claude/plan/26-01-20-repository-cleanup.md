# Repository Cleanup and Reorganization Plan

## Overview

This plan addresses the remaining organizational issues after the user handled git hygiene and .env path issues. The focus is on:
1. Making Excel exports explicit in analysis scripts
2. Moving MLflow files out of root
3. Updating the outdated README
4. Minor root cleanup

## What We're NOT Doing

- ~~Git hygiene~~ - Already handled by user
- ~~.env path fix~~ - Already handled by user
- **Tool subdirectories** - By design (separate training runs should stay isolated)
- **Adding `__init__.py` to tools** - Not needed (tools loaded dynamically by agents)

---

## Desired End State

After implementation:
1. Analysis scripts only generate Excel files when `--export <name>` is provided
2. MLflow files organized in `.mlflow/` directory
3. README accurately reflects the project name (Cobbie) and current architecture
4. Root directory is clean (no dead files)

### Verification
- `uv run python scripts/analyze_evaluation_runs.py --run-ids <id>` prints to terminal only (no Excel)
- `uv run python scripts/analyze_evaluation_runs.py --run-ids <id> --export my_run` creates `reports/Evaluation_YYYY-MM-DD_my_run.xlsx`
- MLflow starts with new paths: `uv run mlflow server ... --backend-store-uri sqlite:///.mlflow/mlflow.sqlite`
- README title says "Cobbie" and project structure matches reality

---

## Phase 1: Make Excel Export Explicit in Analysis Scripts (COMPLETED)

### Overview
Currently, `analyze_training_runs.py` and `analyze_evaluation_runs.py` always create Excel files. We'll make this opt-in via `--export <name>` flag.

### Changes Required

#### 1.1 Modify analyze_training_runs.py

**File**: `scripts/analyze_training_runs.py`

**Current behavior** (lines 503-571): Always creates `reports/{run_name}.xlsx`

**New behavior**:
- Default: Print summary to terminal only
- With `--export <name>`: Create `reports/TRAINING_{date}_{name}.xlsx`

**Argparse changes** (add after line 456):
```python
parser.add_argument(
    "--export",
    type=str,
    default=None,
    metavar="NAME",
    help="Export to Excel file: reports/TRAINING_YYYY-MM-DD_NAME.xlsx",
)
```

**Export logic changes** (wrap lines 503-571):
```python
if args.export:
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"{REPORTS_DIR}/TRAINING_{date_str}_{args.export}.xlsx"
    with pd.ExcelWriter(output_filename, engine="openpyxl") as writer:
        # ... existing Excel writing code ...
    print(f"Export complete: {output_filename}")
else:
    # Print summary to terminal (already happening via print statements above)
    pass
```

#### 1.2 Modify analyze_evaluation_runs.py

**File**: `scripts/analyze_evaluation_runs.py`

**Current behavior** (lines 529-626): Always creates `reports/{run_name}.xlsx`

**New behavior**:
- Default: Print summary to terminal only
- With `--export <name>`: Create `reports/Evaluation_{date}_{name}.xlsx`

**Argparse changes** (add after line 472):
```python
parser.add_argument(
    "--export",
    type=str,
    default=None,
    metavar="NAME",
    help="Export to Excel file: reports/Evaluation_YYYY-MM-DD_NAME.xlsx",
)
```

**Export logic changes** (wrap lines 529-626):
```python
if args.export:
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"{REPORTS_DIR}/Evaluation_{date_str}_{args.export}.xlsx"
    with pd.ExcelWriter(output_filename, engine="openpyxl") as writer:
        # ... existing Excel writing code ...
    print(f"Export complete: {output_filename}")
```

### Success Criteria

#### Automated Verification:
- [x] `uv run python scripts/analyze_evaluation_runs.py --help` shows `--export` option
- [x] Running without `--export` produces no new files in `reports/`

#### Manual Verification:
- [ ] `--export test_run` creates file with expected naming pattern

---

## Phase 2: Move MLflow Files to Subdirectory (COMPLETED)

### Overview
Move MLflow files from root to `.mlflow/` directory to declutter the root.

### Current State
```
cobbie/
├── mlflow.sqlite      # 101MB - tracking database
├── mlruns/            # Run metadata
└── mlartifacts/       # Artifacts (11GB)
```

### Target State
```
cobbie/
└── .mlflow/
    ├── mlflow.sqlite
    ├── mlruns/
    └── mlartifacts/
```

### Changes Required

#### 2.1 Create Directory and Move Files

```bash
mkdir -p .mlflow
mv mlflow.sqlite .mlflow/
mv mlruns .mlflow/
mv mlartifacts .mlflow/
```

#### 2.2 Update CLAUDE.md MLflow Command

**File**: `CLAUDE.md`

**Current** (line ~12):
```bash
uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite --gunicorn-opts "--timeout=120 -w 1"
```

**Updated**:
```bash
uv run mlflow server --host 127.0.0.1 --port 5000 \
  --backend-store-uri sqlite:///.mlflow/mlflow.sqlite \
  --default-artifact-root .mlflow/mlartifacts \
  --gunicorn-opts "--timeout=120 -w 1"
```

#### 2.3 Update README.md MLflow Command

**File**: `README.md` (line 21)

Same change as above.

#### 2.4 Update .gitignore

**File**: `.gitignore`

Replace:
```
mlflow.sqlite
mlruns/
mlartifacts/
```

With:
```
.mlflow/
```

#### 2.5 Check for Hardcoded Paths

Search for any code referencing these paths directly:
- `mlflow.sqlite`
- `mlruns/`
- `mlartifacts/`

These should be minimal since MLflow uses environment variables and CLI args.

### Success Criteria

#### Automated Verification:
- [x] `ls -la .mlflow/` shows mlflow.sqlite, mlruns/, mlartifacts/
- [x] `ls mlflow.sqlite 2>/dev/null || echo "Moved"` prints "Moved"
- [ ] MLflow server starts: `uv run mlflow server --backend-store-uri sqlite:///.mlflow/mlflow.sqlite --default-artifact-root .mlflow/mlartifacts -p 5000`

#### Manual Verification:
- [ ] MLflow UI at http://127.0.0.1:5000 shows existing experiments
- [ ] Training/evaluation runs log correctly to new location

**Implementation Note**: Test MLflow thoroughly before committing. If experiments don't show up, the paths may need adjustment.

---

## Phase 3: Update README.md (COMPLETED)

### Overview
The README is severely outdated. It references:
- Wrong name: "IfcAnswerEngine - V4" (should be "Cobbie")
- Non-existent directories: `src/config/`, `src/engine/`, `examples/`, `docs/`
- Non-existent files: `configuration_migration_guide.md`
- Old architecture with wrong component names
- Frontend that no longer exists

### Changes Required

#### 3.1 Rewrite README

Replace the entire README with an accurate description. Key sections:

**Header**:
```markdown
# Cobbie - Code-Based BIM Information Extraction

An AI system for answering questions about BIM models in IFC format using a multi-agent architecture with dynamic tool creation.
```

**Project Structure** (must match reality):
```
cobbie/
├── api/                  # FastAPI web service
├── baml_src/             # BAML agent definitions
├── baml_client/          # Generated BAML client (auto-generated)
├── src/
│   ├── agents/           # Multi-agent implementations
│   ├── db/               # Database layer and IFC models
│   ├── docs_indexer/     # Documentation retrieval (RAG)
│   ├── schemas/          # Pydantic data models
│   ├── tools/            # Tool ecosystem
│   │   ├── initial/      # Base tools (docs query, web search)
│   │   ├── created/      # Dynamically generated tools
│   │   └── manual/       # Manually curated tools
│   └── util/             # Utilities (metrics, execution, etc.)
├── scripts/              # Training and evaluation scripts
├── analysis/             # Analysis utilities
├── reports/              # Generated reports and figures
├── external/             # External documentation (ifcopenshell)
└── .mlflow/              # MLflow tracking data
```

**Remove**:
- Frontend section (doesn't exist)
- Configuration System section (outdated)
- Mermaid diagrams (outdated component names)
- References to non-existent files

**Keep/Update**:
- Quick start commands (with new MLflow path)
- Prerequisites
- NocoDB section

### Success Criteria

#### Automated Verification:
- [x] `grep "IfcAnswerEngine" README.md` returns no matches
- [x] `grep "Cobbie" README.md` returns matches

#### Manual Verification:
- [ ] README accurately describes the current project
- [ ] All referenced directories/files exist

---

## Phase 4: Clean Root Directory (COMPLETED)

### Overview
Remove dead files from root.

### Changes Required

#### 4.1 Remove Dead Files

```bash
rm sandbox.py           # Empty file (0 bytes)
rm sandbox.ipynb        # Stale experimental notebook
```

### Success Criteria

#### Automated Verification:
- [x] `ls sandbox.* 2>/dev/null || echo "Clean"` prints "Clean"

---

## Implementation Order

1. **Phase 1** (Reports) - Safe, no dependencies
2. **Phase 4** (Root cleanup) - Trivial
3. **Phase 2** (MLflow) - Test carefully before committing
4. **Phase 3** (README) - Do last, after structure is finalized

---

## Summary

| Phase | Task | Risk | Effort |
|-------|------|------|--------|
| 1 | Add `--export` flag to analysis scripts | Low | Medium |
| 2 | Move MLflow to `.mlflow/` | Medium | Low |
| 3 | Rewrite README | Low | Medium |
| 4 | Remove sandbox files | None | Trivial |
