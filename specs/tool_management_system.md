# Tool Management System Specification

**Status**: ✅ ALL PHASES COMPLETE (Phases 1-4)

## Context & Motivation

Cobbie's training phase dynamically creates helper functions/tools to answer BIM-related questions. Currently, 48 tools have been created (~8,431 lines of code), which is starting to exceed the LLM's context window capacity during training.

Without management, the tool library will continue growing unbounded, eventually making it impossible for the LLM to:
- Review all available tools when deciding which to use
- Understand the full toolbox capabilities
- Make informed decisions about tool creation vs enhancement

## Goals

1. **Maintain manageable tool count**: Keep toolbox within context window limits (default: 32 tools)
2. **Prioritize quality over quantity**: Encourage enhancing existing tools rather than always creating new ones
3. **Preserve valuable tools**: Use usage metrics to identify and retain useful tools
4. **Enable cross-run consistency**: Track tool performance across multiple training sessions

## Design Principles

### Hybrid Approach: Enhancement + Deletion

**Enhancement First**: Before creating new tools, the system considers enhancing existing tools with optional parameters. This naturally reduces tool proliferation while building more capable, modular tools.

**Usage-Based Deletion**: When tool count exceeds the limit, delete tools based on actual usage metrics (not arbitrary LLM decisions). This preserves tools that demonstrably contribute to correct answers.

### Question-Based Metrics

All metrics track question counts (not time-based), making them robust to irregular training schedules:
- `questions_when_included`: How often tool was in the available toolbox
- `questions_when_called`: How often tool was actually invoked
- `questions_correct_contribution`: Contribution to correct answers
- `questions_wrong_contribution`: Contribution to wrong answers

### Grace Period

New tools are immune from deletion for the first N questions (default: 25). This accommodates:
- Diverse question types (tools may be specialized)
- Sporadic usage patterns (tools may be needed infrequently)
- Fair evaluation period (sufficient opportunities to prove value)

### Cross-Run Tracking

Training typically spans multiple runs with `--start` and `--end` flags. The system tracks global question numbers across runs, ensuring consistent metrics and supporting the `--continue` flag for resuming training.

---

## Implementation Plan

### **Phase 1: Tool Usage Tracking Foundation**

#### **1.1 Create Tool Metadata Storage** ✅ COMPLETED
**Files**:
- `src/db/models.py` - Added `ToolUsageStats` SQLModel (auto-generated)
- `src/db/query.py` - Added 6 query functions (~120 lines)
- `test/test_tool_metadata.py` - Comprehensive test suite (12 tests, all passing)

**Implementation Notes**:
- Table created in database and SQLModel auto-generated via `sqlacodegen`
- All queries use `with Session(db.ENGINE)` pattern (not raw SQL)
- Functions return SQLModel objects, integrated with existing query patterns
- Table initialization handled by SQLModel metadata (no manual CREATE TABLE)

**Query Functions** (in `src/db/query.py`):
- `register_new_tool(name, global_question_num)` - Initialize entry using `session.merge()`
- `increment_tool_inclusion(tool_names, global_question_num)` - Track available tools
- `update_tool_usage(tool_names, is_correct, global_question_num)` - Track usage + contribution
- `get_tool_stats(tool_name)` - Returns `ToolUsageStats` object or None
- `get_all_tool_stats()` - Returns `List[ToolUsageStats]`
- `get_last_question_processed()` - Returns `Optional[int]` for --continue flag

#### **1.2 Parse Execution History for Tool Usage** ✅ COMPLETED
**File**: `src/util/extract_tool_usage.py` (new, ~60 lines)
**Test**: `test/test_extract_tool_usage.py` (manual test suite)

**Implementation Notes**:
- Uses `CREATED_TOOLS_PATH` from config for absolute paths (robust across environments)
- Explicitly documented to expect `execution_history` (not full conversation history)
- Prevents false positives from tools listed in system prompts
- Tested with both mock and real Cobbie execution histories

**Function**: `extract_tools_used(execution_history: str) -> List[str]`
- Regex pattern: `r'\b([a-z_][a-z0-9_]*)\s*\('` (function calls only)
- Filter to tools existing in `CREATED_TOOLS_PATH`
- Return deduplicated list (preserves order of first occurrence)
- All code review checks passed (ruff, ty, pyright)

#### **1.3 Update Tool Saving** ✅ COMPLETED
**File**: `src/util/save_new_tool.py` (modified ~8 lines)

**Implementation Notes**:
- Added optional parameter: `global_question_num: Optional[int] = None`
- Added import: `from src.db.query import register_new_tool`
- Calls `register_new_tool(name, global_question_num)` when parameter provided
- Updated docstring with parameter documentation
- Backward compatible (global_question_num is optional)

#### **1.4 Integrate Usage Tracking in Training Loop** ✅ COMPLETED
**File**: `scripts/run_training_phase.py` (modified ~25 lines)

**Implementation Notes**:
- Added imports: `extract_tools_used`, `increment_tool_inclusion`, `update_tool_usage`
- Added `global_question_num: int` field to `Context` class
- Updated `handle_start_state`: Tracks tool inclusion via `increment_tool_inclusion()`
- Updated `handle_verify_answer`: Extracts and tracks tool usage via `update_tool_usage()`
- Updated `handle_decide_tool_fate`: Passes `global_question_num` to `save_new_tool()` (2 locations)
- Updated main loop: Initializes Context with `global_question_num = args.start + idx`
- Added MLflow metric logging: `mlflow.log_metric("num_tools_used", len(tools_used), step=global_question_num)`
- Fixed type safety issue: Added None check for `mlflow.active_run()` in previous_total calculation
- All code review checks passed (ruff, ty, pyright)

---

### **Phase 2: Unified Tool Creation/Enhancement Agent** ✅ COMPLETED

#### **2.1 Update NewToolAnalysis Schema** ✅ COMPLETED
**File**: `baml_src/schemas.baml` (modified)

```baml
class NewToolAnalysis {
    thoughts string
    action "create_new" | "enhance_existing" | "none"
    tool_name string  // Tool to create OR tool to enhance
    tool_description string  // Description OR enhancement description
}
```

Legacy `new_tool` field removed for clarity.

#### **2.2 Update identify_helper_function.baml** ✅ COMPLETED
**File**: `baml_src/identify_helper_function.baml` (modified ~30 lines)
**File**: `src/agents/identify_helper_function.py` (fixed to use new schema)

Add tool management strategy to instructions:
- Consider enhancing existing tools with optional parameters
- Create new tools only if distinctly different functionality
- Enhancement must maintain backward compatibility
- Set `action` field appropriately

**Implementation Notes**:
- Updated BAML prompt with enhancement vs creation decision criteria
- Fixed `identify_helper_function.py` to use `action`, `tool_name`, `tool_description` fields
- Fixed type errors in test code

#### **2.3 Unify create_helper_function with Enhancement** ✅ COMPLETED
**File**: `src/agents/create_helper_function.py` (modified ~50 lines)
**File**: `baml_src/create_helper_function.baml` (modified ~40 lines)

**Add optional parameter**:
```python
def create_helper_function(
    # ... existing params ...
    existing_tool_code: Optional[str] = None  # If provided, enhance mode
) -> Tuple[NewHelperFunction, Collector, str]:
```

**BAML conditional prompt**:
```baml
{% if existing_tool_code %}
    ## Task: ENHANCE EXISTING TOOL
    [enhancement instructions - maintain backward compatibility]
{% else %}
    ## Task: CREATE NEW TOOL
    [creation instructions]
{% endif %}
[... common instructions ...]
```

#### **2.4 Update Training State Machine** ✅ COMPLETED
**File**: `scripts/run_training_phase.py` (modified ~40 lines)

**Handle enhancement action**:
```python
if tool_analysis.action == "enhance_existing":
    tool_path = Path(f"src/tools/created/{tool_analysis.tool_name}.py")
    existing_code = tool_path.read_text()

    new_tool, collector, history = create_helper_function(
        # ... params ...
        existing_tool_code=existing_code
    )
elif tool_analysis.action == "create_new":
    new_tool, collector, history = create_helper_function(
        # ... params ...
    )
```

---

### **Phase 3: Usage-Based Tool Deletion** ✅ COMPLETED

#### **3.1 Deletion Score Calculation** ✅ COMPLETED
**File**: `src/db/query.py` (added ~113 lines)
**File**: `src/util/delete_tool.py` (new, ~35 lines)
**File**: `src/util/__init__.py` (updated exports)
**Test**: `test/test_tool_deletion.py` (6 tests, all passing)

**Implementation Notes**:
- Deletion score ranges 0-100 (higher = more deletable)
- Grace period protection: score = 0.0 if age < grace_period
- Never included tools: score = 100.0 (instant deletion)
- Weighted formula combines age, call rate, success rate, failure penalty
- All type checks passed (ruff, ty, pyright)

**Deletion Score Formula** (implemented):
```python
age = current_question_num - created_at_question

if age < grace_period:
    return 0.0  # Protected
elif questions_when_included == 0:
    return 100.0  # Never used

# Calculate rates
call_rate = questions_when_called / questions_when_included
success_rate = questions_correct / questions_when_called if questions_when_called > 0 else 0.0
failure_rate = questions_wrong / questions_when_called if questions_when_called > 0 else 0.0

# Weighted score (0-100)
age_score = min(age / 100.0, 1.0) * 20
call_score = (1.0 - call_rate) * 30
success_score = (1.0 - success_rate) * 25
failure_score = failure_rate * 25

return min(age_score + call_score + success_score + failure_score, 100.0)
```

**Functions** (in `src/db/query.py`):
- `calculate_deletion_score(tool_stats, current_question_num, grace_period)` - Calculate score for one tool
- `get_tools_ranked_by_deletion_score(current_question_num, grace_period)` - Return ranked list
- `delete_tool_from_db(tool_name)` - Delete metadata from database
- `initialize_tool_metadata(global_question_num)` - Initialize existing tools

**Utility Function** (in `src/util/delete_tool.py`):
- `delete_tool(tool_name)` - Delete tool from filesystem and database

#### **3.2 Integrate Deletion Check in Training Loop** ✅ COMPLETED
**File**: `scripts/run_training_phase.py` (modified ~40 lines)

**Implementation Notes**:
- Added `max_tools` and `grace_period` fields to `Context` class
- Updated `handle_start_state()` to check tool count before loading
- Deletes lowest-scoring tools when count exceeds `max_tools`
- Logs deletion metrics to MLflow
- All type checks passed

**Deletion check** (in `handle_start_state`):
```python
if len(current_tools) > context.max_tools:
    num_to_delete = len(current_tools) - context.max_tools
    ranked_tools = get_tools_ranked_by_deletion_score(
        current_question_num=context.global_question_num,
        grace_period=context.grace_period
    )

    # Delete top N by score
    for tool_name, score in ranked_tools[:num_to_delete]:
        delete_tool(tool_name)

    # Log to MLflow
    mlflow.log_metrics({
        f"tools_deleted_at_q{context.global_question_num}": deleted_count,
        "current_tool_count": len(get_created_tools())
    })
```

---

### **Phase 4: Configuration & Integration** ✅ COMPLETED

#### **4.1 Add CLI Parameters** ✅ COMPLETED
**File**: `scripts/run_training_phase.py` (modified)

**Implementation Notes**:
- Added `--max-tools` argument (default: 32)
- Added `--grace-period` argument (default: 25)
- Parameters logged to MLflow for tracking
- Passed to Context initialization

```python
parser.add_argument("--max-tools", type=int, default=32,
                   help="Maximum number of tools to maintain (default: 32)")
parser.add_argument("--grace-period", type=int, default=25,
                   help="Questions to protect new tools from deletion (default: 25)")

# Log to MLflow
mlflow.log_params({
    "max_tools": args.max_tools,
    "grace_period": args.grace_period,
})

# Pass to Context
context = Context(
    qa_pair=qa_pair,
    global_question_num=global_question_num,
    max_tools=args.max_tools,
    grace_period=args.grace_period,
)
```

#### **4.2 Initialize Metadata on Training Start** ✅ COMPLETED
**File**: `scripts/run_training_phase.py` (modified)
**File**: `src/db/query.py` (added `initialize_tool_metadata()`)

**Implementation Notes**:
- Initializes metadata for existing tools without database entries
- Called at start of training run after MLflow setup
- Logs count of initialized tools

```python
from src.db.query import initialize_tool_metadata

initialized_count = initialize_tool_metadata(args.start)
if initialized_count > 0:
    _logger.info(f"Initialized metadata for {initialized_count} existing tools")
```

#### **4.3 Support --continue Flag Enhancement** ✅ COMPLETED
**File**: `scripts/run_training_phase.py` (modified ~20 lines)

**Implementation Notes**:
- Auto-detects last processed question from database
- Resumes training from correct index
- Overrides `--start` parameter when appropriate
- Works with existing `--continue` flag and MLflow run continuation

```python
if args.continue_run:
    from src.db.query import get_last_question_processed

    last_processed = get_last_question_processed()
    if last_processed is not None:
        resume_index = last_processed + 1
        _logger.info(f"--continue: resuming from question {resume_index}")

        # Override start if not explicitly provided
        if args.start == 0:  # Default value
            args.start = resume_index
            _logger.info(f"Auto-adjusted start index to {args.start}")
    else:
        _logger.info("--continue: no previous progress found")
```

---

## Implementation Order & Testing

### Step-by-Step Rollout

1. **Phase 1.1**: Database schema + metadata functions
   - Test: Create/query metadata with various global_question_num values

2. **Phase 1.2**: Execution history parser
   - Test: Unit tests with sample histories

3. **Phase 1.3 + 1.4**: Integrate tracking in training
   - Test: Run 3-5 questions, verify database metrics

4. **Phase 2.1 + 2.2**: Schema + prompt changes
   - Test: Run identify_helper_function, verify new action field

5. **Phase 2.3 + 2.4**: Unified create/enhance agent
   - Test: Create new tool and enhance existing tool

6. **Phase 3**: Deletion mechanism
   - Test: Create 10 dummy tools, set MAX_TOOLS=5, verify deletion

7. **Phase 4**: Configuration polish
   - Test: Full training run with all features, test --continue

### Success Metrics

- Tool count maintained below MAX_TOOLS
- Enhancement rate > 20% (model prefers enhancing over creating)
- Deletion targets low-usage tools (score < 0.1)
- No tool deleted within grace period
- Tracking works correctly across multiple training runs

---

## Files Summary

**All Files Completed** ✅:

**Phase 1 Files**:
- `src/db/models.py` - Added `ToolUsageStats` model (auto-generated)
- `src/db/query.py` - Added 6 tracking query functions (~120 lines)
- `test/test_tool_metadata.py` - Test suite (~265 lines, 12 tests passing)
- `src/util/extract_tool_usage.py` - Tool usage extractor (~60 lines)
- `test/test_extract_tool_usage.py` - Manual test suite for real Cobbie runs
- `src/util/save_new_tool.py` - Updated to register tools (~8 lines modified)
- `scripts/run_training_phase.py` - Integrated usage tracking (~25 lines modified)

**Phase 2 Files**:
- `baml_src/schemas.baml` - Updated `NewToolAnalysis` schema
- `baml_src/identify_helper_function.baml` - Added enhancement decision logic
- `src/agents/identify_helper_function.py` - Fixed to use new schema fields
- `baml_src/create_helper_function.baml` - Added enhancement mode support
- `src/agents/create_helper_function.py` - Unified creation/enhancement

**Phase 3 Files**:
- `src/db/query.py` - Added 4 deletion functions (~113 lines)
- `src/util/delete_tool.py` - Tool deletion utility (new, ~35 lines)
- `src/util/__init__.py` - Updated exports
- `test/test_tool_deletion.py` - Deletion test suite (new, ~110 lines, 6 tests passing)
- `scripts/run_training_phase.py` - Integrated deletion check (~40 lines modified)

**Phase 4 Files**:
- `scripts/run_training_phase.py` - CLI params, metadata init, --continue enhancement (~35 lines modified)

**Total Implementation**: All phases complete (100%)
**No breaking changes**: All backward compatible
**All tests passing**: 18 tests across 2 test files

---

## Configuration Defaults

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `--max-tools` | 32 | Balance between capability and context window |
| `--grace-period` | 25 | Sufficient questions to span diverse types |

Both parameters are configurable via CLI for tuning based on dataset characteristics.

---

## Usage

```bash
# Start new training with tool management
uv run scripts/run_training_phase.py --start 0 --end 50 --max-tools 32 --grace-period 25

# Continue previous training (auto-resumes from last processed question)
uv run scripts/run_training_phase.py --continue --end 100

# Adjust tool management parameters
uv run scripts/run_training_phase.py --start 0 --end 50 --max-tools 20 --grace-period 30
```

---

## Bug Fixes

**Fixed during Phase 3/4 implementation**:
- `src/agents/identify_helper_function.py` - Updated to use new `action`, `tool_name`, `tool_description` fields instead of legacy `new_tool`, `new_tool_name`, `new_tool_description`
- Fixed type errors in test code (token metrics calculation)
- All code review checks passing (ruff, ty, pyright)
