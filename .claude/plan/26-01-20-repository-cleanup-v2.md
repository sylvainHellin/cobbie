# Repository Cleanup and Reorganization Plan (Updated)

## Overview

This plan extends the original cleanup with additional structural improvements:
1. ~~Making Excel exports explicit in analysis scripts~~ (COMPLETED)
2. ~~Moving MLflow files out of root~~ (COMPLETED)
3. ~~Updating the README (minor fixes from comments)~~ (COMPLETED)
4. ~~Minor root cleanup~~ (COMPLETED)
5. ~~Move API to separate web repo~~ (COMPLETED)
6. ~~Restructure output directories~~ (COMPLETED)

---

## Phase 3.1: Fix README Content (Minor Updates)

### Changes Required

**File**: `README.md`

1. **Line 3**: Already correct ("AI Agent")
2. **Line 7**: Remove comment, reorder features to emphasize inference first
3. **Line 22-28**: Replace installation steps with `uv sync`
4. **Line 36**: Keep gunicorn-opts (research confirms they're useful):
   - `--timeout=120`: Necessary - default is 30s, which causes timeouts with large artifacts
   - `-w 1`: Optional but recommended for SQLite to avoid locking issues

**Updated Installation section**:
```markdown
### Installation

```bash
git clone <repository-url>
cd cobbie
uv sync
cp .env.example .env  # Edit with your API keys
```
```

**Updated Features section** (inference focus first):
```markdown
## Features

- **Dynamic IFC Model Exploration**: Intelligent navigation and querying of BIM models in IFC format
- **Multi-Agent Architecture**: Specialized agents for programming, assessment, and correction tasks
- **Automated Tool Creation**: Dynamically generates Python functions during training for reuse in inference
- **MLflow Integration**: Complete experiment tracking and logging
```

### Success Criteria

#### Automated Verification:
- [x] `grep "uv sync" README.md` returns match
- [x] No HTML comments remain in README.md

---

## Phase 5: Move API to Separate Web Repository

### Overview

The FastAPI backend (`api/`) should be moved to combine with the frontend in a dedicated web repository. This separates business logic (cobbie) from web interface concerns.

### Current State
```
cobbie/                     cobbie-demo/
├── api/                    ├── src/           (React frontend)
│   ├── main.py             ├── package.json
│   └── start_server.py     └── ...
└── src/
    └── (business logic)
```

### Target State
```
cobbie/                     cobbie-web/  (renamed from cobbie-demo)
├── src/                    ├── api/           (moved from cobbie)
│   └── (business logic)    │   ├── main.py
└── ...                     │   └── start_server.py
                            ├── frontend/      (was src/)
                            └── ...
```

### Changes Required

#### 5.0 Rename cobbie-demo to cobbie-web

```bash
cd /Users/sylvainhellin/code
mv cobbie-demo cobbie-web
```

Update git remote if needed.

#### 5.1 In cobbie-web repo

1. Create `api/` directory
2. Copy `cobbie/api/` contents
3. Update imports to use cobbie as an installed package:
   ```python
   # Instead of: from src.agents import Cobbie
   # Use: from cobbie.agents import Cobbie
   ```
4. Add `cobbie` as a dependency in package requirements

#### 5.2 In cobbie repo

1. Remove `api/` directory
2. Ensure package is installable (`pip install -e .` or `uv pip install -e .`)
3. Update README to remove FastAPI section, add reference to cobbie-web
4. Update CLAUDE.md to remove API commands

#### 5.3 Update CLAUDE.md

**Remove**:
```markdown
### Backend (Python)
- **Dev Server**: `uv run python api/start_server.py` or `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`
```

**Add reference to cobbie-web for API development**

### Success Criteria

#### Automated Verification:
- [x] `ls api/` in cobbie returns error (directory removed)
- [x] `grep "api/start_server" README.md` returns no matches
- [x] `grep "uvicorn" CLAUDE.md` returns no matches

#### Manual Verification:
- [ ] cobbie-web API starts successfully with cobbie installed
- [ ] API endpoints work as before

---

## Phase 6: Restructure Output Directories

### Overview

Reorganize `external/`, `reports/`, and `analysis/` for cleaner structure.

### Current State
```
cobbie/
├── external/               # ifcopenshell-docs submodule
│   └── ifcopenshell-docs/
├── reports/                # Output: Excel files, figures
└── analysis/               # Code + data for baseline comparison
    ├── baseline_qa/        # Baseline implementation
    └── data/               # Cached baseline data
```

### Target State
```
cobbie/
├── src/
│   └── docs_indexer/
│       └── external/       # Moved: ifcopenshell-docs submodule
│           └── ifcopenshell-docs/
├── outputs/                # All generated outputs
│   ├── reports/            # Moved: evaluation reports, figures
│   └── cache/              # Moved from analysis/data/
└── baselines/              # Renamed from analysis/
    └── baseline_qa/        # Baseline implementation code
```

### Changes Required

#### 6.1 Move external/ to src/docs_indexer/external/

```bash
git mv external src/docs_indexer/external
```

**Update `src/docs_indexer/indexer.py`**:
- Change path from `external/ifcopenshell-docs/` to `src/docs_indexer/external/ifcopenshell-docs/`

**Update any scripts referencing external/**

#### 6.2 Create outputs/ structure

```bash
mkdir -p outputs
git mv reports outputs/
git mv analysis/data/baseline_cache outputs/cache
```

#### 6.3 Rename analysis/ to baselines/

```bash
git mv analysis baselines
```

**Update imports in**:
- `scripts/run_evaluation.py` (imports from analysis.baseline_qa)
- Any other scripts using baseline_qa

#### 6.4 Update .gitignore

Replace:
```
reports
analysis/data/baseline_cache
```

With:
```
outputs/
```

#### 6.5 Update README.md project structure

```markdown
## Project Structure

```
cobbie/
├── baml_src/             # BAML agent definitions
├── baml_client/          # Generated BAML client (auto-generated)
├── src/
│   ├── agents/           # Multi-agent implementations
│   ├── db/               # Database layer and IFC models
│   ├── docs_indexer/     # Documentation retrieval (RAG)
│   │   └── external/     # IfcOpenShell documentation (submodule)
│   ├── schemas/          # Pydantic data models
│   ├── tools/            # Tool ecosystem
│   │   ├── initial/      # Base tools (docs query, web search)
│   │   ├── created/      # Dynamically generated tools
│   │   └── manual/       # Manually curated tools
│   └── util/             # Utilities (metrics, execution, etc.)
├── scripts/              # Training and evaluation scripts
├── baselines/            # Baseline implementations for comparison
├── outputs/              # Generated reports, figures, cache
└── .mlflow/              # MLflow tracking data
```
```

### Success Criteria

#### Automated Verification:
- [x] `ls external/` returns error (moved)
- [x] `ls src/docs_indexer/external/ifcopenshell-docs/` succeeds
- [x] `ls outputs/reports/` succeeds
- [x] `ls baselines/baseline_qa/` succeeds
- [x] `uv run python -c "from baselines.baseline_qa import baseline_bim_qas"` succeeds

#### Manual Verification:
- [x] `src/docs_indexer/indexer.py` runs without path errors
- [ ] Baseline evaluation still works

---

## Implementation Order

1. **Phase 3.1** (README fixes) - Quick, no dependencies
2. **Phase 6** (Directory restructure) - Do before API move to stabilize structure
3. **Phase 5** (API move) - Do last, requires coordination with cobbie-demo

---

## Summary

| Phase | Task | Risk | Effort |
|-------|------|------|--------|
| 3.1 | Fix README content | None | Trivial |
| 5 | Move API to cobbie-web | Medium | Medium |
| 6 | Restructure directories | Low | Medium |
