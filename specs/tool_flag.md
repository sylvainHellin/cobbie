
# Implementation Plan: Add `--tools` Flag for Ablation Studies

## Overview
Add a `--tools` CLI flag to the evaluation script to control which tool directories are loaded. This enables ablation studies to compare system performance with different tool configurations (no tools, only initial tools, only created tools, combinations, etc.).

## Requirements
- Add `--tools` flag accepting values: 'created', 'initial', 'manual', 'none'
- Support multiple space-separated values (e.g., `--tools created initial`)
- Default to `['created', 'initial']` to maintain backward compatibility
- Log tool configuration in MLflow for experiment tracking

## Critical Files

### Files to Create
1. **`src/util/load_tools.py`** - New generic tool loading utility

### Files to Modify
2. **`scripts/run_evaluation.py`** - Add CLI flag and update tool loading
3. **`src/config.py`** - Add tool directory path constants

## Implementation Steps

### Step 1: Add Tool Directory Paths to Config

**File:** `src/config.py`

**Location:** After line 13 (after `CREATED_TOOLS_PATH` definition)

**Add:**
```python
INITIAL_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/initial")
MANUAL_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/manual")
```

### Step 2: Create Generic Tool Loading Utility

**File:** `src/util/load_tools.py` (new file)

**Purpose:** Provide functions to load tools from any directory and build tools dictionary based on CLI flags

**Key Functions:**
- `load_tools_from_directory(directory_path, import_base)` - Generic loader using importlib
- `get_initial_tools()` - Load from `src/tools/initial/`
- `get_manual_tools()` - Load from `src/tools/manual/`
- `get_created_tools()` - Load from `src/tools/created/`
- `build_tools_dict(tool_categories: List[str])` - Main function that builds tools dict based on requested categories

**Implementation Details:**
- Use same pattern as `get_created_tools.py`: importlib + inspect
- Handle missing directories gracefully (warn, don't crash)
- Return empty dict for 'none' category
- Log what's loaded for each category

**Pattern from `get_created_tools.py`:**
```python
# Get Python files (excluding __init__.py)
# Use importlib.import_module(f"{import_base}.{module_name}")
# Use inspect.getmembers() to extract functions
# Filter: inspect.isfunction() and fn.__module__ == module.__name__
# Don't auto-delete broken files (that's training-specific)
```

**Delete current `get_created_tools.py`**
- Delete this file (the function `get_created_tool` should now be implemented in the `load_tools.py`)
- update all the import of this `get_created_tool` in other files

### Step 3: Add CLI Argument

**File:** `scripts/run_evaluation.py`

**Location:** After line 553 (after `--reset-tool-metrics`)

**Add:**
```python
parser.add_argument(
    "--tools",
    "-t",
    nargs="*",  # Accept space-separated values
    default=["created", "initial"],
    choices=["created", "initial", "manual", "none"],
    help="Tool categories to include (default: created initial)",
)
```

### Step 4: Update Imports

**File:** `scripts/run_evaluation.py`

**Location:** Line 27

**Change:**
```python
# From:
from src.util import get_created_tools

# To:
from src.util.load_tools import build_tools_dict
```

**Note:** Also update line 36 `from src.tools.initial import query_ifcopenshell_docs, web_search`

### Step 5: Replace Tool Loading Logic

**File:** `scripts/run_evaluation.py`

**Location:** Lines 589-601

**Replace:**
```python
# Prepare tools for COBBIE
tools_dict = {
    "query_ifcopenshell_docs": query_ifcopenshell_docs,
    "web_search": web_search,
}

# Add all created tools from src.tools/created/
try:
    created_tools = get_created_tools()
    tools_dict.update(created_tools)
    logger.info(f"Loaded {len(created_tools)} created tools for COBBIE")
except Exception as e:
    logger.warning(f"Could not load created tools: {e}")
```

**With:**
```python
# Prepare tools for COBBIE based on --tools flag
tools_dict = build_tools_dict(args.tools)
```

**Rationale:** All loading logic and error handling now in `build_tools_dict()`

### Step 6: Enhance MLflow Logging

**File:** `scripts/run_evaluation.py`

**Location:** Lines 624-631

**Modify:**
```python
mlflow.log_params(
    {
        "model_name": "glm-4.6",
        "provider_name": "zai",
        "component": "COBBIE",
        "tool_categories": ", ".join(sorted(args.tools)),  # NEW
        "tools": ", ".join(sorted(tools_dict.keys())),
        "tools_count": len(tools_dict),
    }
)
```

**Purpose:** Log both requested categories and actual tools loaded

### Step 7: Update Help Documentation

**File:** `scripts/run_evaluation.py`

**Location:** Lines 499-509 (epilog section)

**Add examples:**
```python
epilog="""
Examples:
  # Basic evaluation with first 5 samples
  uv run scripts/run_evaluation.py --start 0 --nb-samples 5

  # Evaluate samples 10-20
  uv run scripts/run_evaluation.py --start 10 --nb-samples 10

  # Ablation study: no tools
  uv run scripts/run_evaluation.py --start 0 --nb-samples 10 --tools none

  # Ablation study: only manual tools
  uv run scripts/run_evaluation.py --start 0 --nb-samples 10 --tools manual

  # Combine tool types
  uv run scripts/run_evaluation.py --start 0 --nb-samples 10 --tools created manual

  # Evaluate with debug logging
  uv run scripts/run_evaluation.py --start 0 --nb-samples 3 --log-level DEBUG
        """,
```

## Design Decisions

### Why create new `load_tools.py` instead of modifying `get_created_tools.py`?
- **Cleaner interface:** Generic `build_tools_dict(categories)` is clearer than modifying existing function

### How does 'none' work?
- Returns empty dict `{}`
- COBBIE agent runs without custom tools (only python interpreter if that's handled separately)
- Useful for baseline comparison

### Manual tools directory structure
- Currently unused but exists with ~26 tools
- Follow same pattern as created tools (`.py` files with functions)
- May have internal imports (e.g., `state.py`) - test this during implementation

## Testing Plan

After implementation, test these scenarios:

1. **Default behavior (backward compatibility):**
   ```bash
   uv run scripts/run_evaluation.py --start 0 --nb-samples 1
   ```
   Should load initial + created tools

2. **No tools:**
   ```bash
   uv run scripts/run_evaluation.py --start 0 --nb-samples 1 --tools none
   ```
   Should run with `tools_count: 0`

3. **Single category:**
   ```bash
   uv run scripts/run_evaluation.py --start 0 --nb-samples 1 --tools manual
   ```
   Should load ~26 manual tools

4. **Multiple categories:**
   ```bash
   uv run scripts/run_evaluation.py --start 0 --nb-samples 1 --tools initial created
   ```
   Should load both

5. **MLflow verification:**
   - Check that `tool_categories` param shows in MLflow UI
   - Verify `tools_count` matches expected count
   - Confirm different runs can be compared by tool configuration

6. **Error handling:**
   - Test with empty created directory
   - Test with broken tool file in manual directory

## Potential Issues

2. **Name collisions** - If same function name exists in multiple directories, last loaded wins. Document this behavior.

3. **Performance** - Loading 50+ created + 26 manual tools might be slow, but training already does this, so should be fine.

## Assumptions
- Manual tools follow same structure as created tools (functions in .py files)
- Tool directories exist (code handles missing directories gracefully)
- Backward compatibility is critical (default behavior must not change)
- MLflow server is running for experiment tracking
