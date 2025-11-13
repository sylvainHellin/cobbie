# Tool Management System Specification

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

#### **1.1 Create Tool Metadata Storage**
**File**: `src/util/tool_metadata.py` (new, ~90 lines)

**Database Schema**: Add table `tool_usage_stats`
```sql
CREATE TABLE tool_usage_stats (
    tool_name TEXT PRIMARY KEY,
    questions_when_included INTEGER DEFAULT 0,
    questions_when_called INTEGER DEFAULT 0,
    questions_correct_contribution INTEGER DEFAULT 0,
    questions_wrong_contribution INTEGER DEFAULT 0,
    created_at_question INTEGER DEFAULT 0,
    last_question_processed INTEGER DEFAULT 0
)
```

**Functions**:
- `init_tool_metadata_table()` - Create table if not exists
- `register_new_tool(name, global_question_num)` - Initialize entry
- `increment_tool_inclusion(tool_names, global_question_num)` - Track available tools
- `update_tool_usage(tool_names, is_correct, global_question_num)` - Track usage + contribution
- `get_tool_stats(tool_name)` - Retrieve stats for one tool
- `get_all_tool_stats()` - Retrieve all stats for deletion decisions
- `get_last_question_processed()` - For --continue flag support

#### **1.2 Parse Execution History for Tool Usage**
**File**: `src/util/extract_tool_usage.py` (new, ~40 lines)

**Function**: `extract_tools_used(execution_history: str) -> List[str]`
- Regex pattern: `r'\b([a-z_][a-z0-9_]*)\s*\('` (function calls only)
- Filter to tools existing in `/src/tools/created/`
- Return deduplicated list

#### **1.3 Update Tool Saving**
**File**: `src/util/save_new_tool.py` (modify ~5 lines)

- Add parameter: `global_question_num: int`
- Call `register_new_tool(name, global_question_num)` after saving

#### **1.4 Integrate Usage Tracking in Training Loop**
**File**: `scripts/run_training_phase.py` (modify ~30 lines)

**Global question tracking**:
```python
global_question_num = args.start  # Start from --start flag
for idx in range(args.start, args.end):
    global_question_num = idx
```

**Before Cobbie execution**:
```python
available_tools = [f.stem for f in Path("src/tools/created").glob("*.py")]
increment_tool_inclusion(available_tools, global_question_num)
```

**After answer verification**:
```python
tools_used = extract_tools_used(execution_history)
update_tool_usage(tools_used, is_correct, global_question_num)
mlflow.log_metric("num_tools_used", len(tools_used), step=global_question_num)
```

---

### **Phase 2: Unified Tool Creation/Enhancement Agent**

#### **2.1 Update NewToolAnalysis Schema**
**File**: `baml_src/schemas.baml` (modify ~8 lines)

```baml
class NewToolAnalysis {
    thoughts string
    action "create_new" | "enhance_existing" | "none"
    tool_name string  // Tool to create OR tool to enhance
    tool_description string  // Description OR enhancement description
}
```

Remove legacy `new_tool` field for clarity.

#### **2.2 Update identify_helper_function.baml**
**File**: `baml_src/identify_helper_function.baml` (modify ~30 lines)

Add tool management strategy to instructions:
- Consider enhancing existing tools with optional parameters
- Create new tools only if distinctly different functionality
- Enhancement must maintain backward compatibility
- Set `action` field appropriately

#### **2.3 Unify create_helper_function with Enhancement**
**File**: `src/agents/create_helper_function.py` (modify ~50 lines)
**File**: `baml_src/create_helper_function.baml` (modify ~40 lines)

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

#### **2.4 Update Training State Machine**
**File**: `scripts/run_training_phase.py` (modify ~40 lines)

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

### **Phase 3: Usage-Based Tool Deletion**

#### **3.1 Consolidated Tool Management**
**File**: `src/util/tool_management.py` (new, ~100 lines)

**Deletion Score Formula**:
```python
questions_since_creation = current_question_num - created_at_question

if questions_since_creation < grace_period:
    score = float('inf')  # Immune
elif questions_when_included == 0:
    score = 0  # Never included
elif questions_when_called == 0:
    score = 0.01  # Never used
else:
    inclusion_rate = questions_when_included / questions_since_creation
    usage_rate = questions_when_called / questions_when_included
    success_rate = questions_correct / (questions_correct + questions_wrong) if total > 0 else 0.5

    score = inclusion_rate × usage_rate × (1 + success_rate)
```

**Functions**:
- `calculate_deletion_scores(current_question_num, grace_period)` - Score all tools
- `select_tools_for_deletion(num_to_delete, current_question_num, grace_period)` - Return lowest-scored tools
- `delete_tools(tool_names, current_question_num, reason)` - Delete files and log

#### **3.2 Integrate Deletion Check in Training Loop**
**File**: `scripts/run_training_phase.py` (modify ~20 lines)

**At start of each question**:
```python
current_tool_count = len(list(Path("src/tools/created").glob("*.py")))

if current_tool_count > MAX_TOOLS:
    num_to_delete = current_tool_count - MAX_TOOLS
    tools_to_delete = select_tools_for_deletion(num_to_delete, global_question_num, GRACE_PERIOD)
    delete_tools(tools_to_delete, global_question_num, reason=f"Exceeded max ({MAX_TOOLS})")
```

---

### **Phase 4: Configuration & Integration**

#### **4.1 Add CLI Parameters**
**File**: `scripts/run_training_phase.py` (modify ~20 lines)

```python
parser.add_argument("--max-tools", type=int, default=32)
parser.add_argument("--grace-period", type=int, default=20)
```

#### **4.2 Initialize Metadata on Training Start**
**File**: `scripts/run_training_phase.py` (modify ~5 lines)

```python
from src.util.tool_metadata import init_tool_metadata_table
init_tool_metadata_table()
```

#### **4.3 Support --continue Flag Enhancement**
**File**: `scripts/run_training_phase.py` (modify ~10 lines)

```python
if args.continue_run:
    last_processed = get_last_question_processed()
    if last_processed is not None and last_processed >= args.start:
        args.start = last_processed + 1
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

**New Files** (3):
- `src/util/tool_metadata.py` (~90 lines)
- `src/util/extract_tool_usage.py` (~40 lines)
- `src/util/tool_management.py` (~100 lines)

**Modified Files** (6):
- `baml_src/schemas.baml` (~8 lines)
- `baml_src/identify_helper_function.baml` (~30 lines)
- `baml_src/create_helper_function.baml` (~40 lines)
- `src/agents/create_helper_function.py` (~50 lines)
- `src/util/save_new_tool.py` (~5 lines)
- `scripts/run_training_phase.py` (~115 lines)

**Total**: ~230 lines new, ~248 lines modified
**No breaking changes**: All backward compatible

---

## Configuration Defaults

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `--max-tools` | 32 | Balance between capability and context window |
| `--grace-period` | 20 | Sufficient questions to span diverse types |

Both parameters are configurable via CLI for tuning based on dataset characteristics.
