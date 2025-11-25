Tool Management System Implementation Plan: Phases 2-4

Overview

Complete the tool management system by implementing:
- Phase 2: Unified tool creation/enhancement agent (prefer enhancement at
70%+ overlap)
- Phase 3: Usage-based deletion when count exceeds 32 tools
- Phase 4: CLI configuration and initialization

Phase 1 is complete with full usage tracking in place.

Design Decisions

1. Enhancement Threshold: Moderate (70%+ functionality overlap) - balances
tool capability with complexity
2. Iteration Limit: 15 iterations for both creation and enhancement -
consistent limits
3. Deletion Formula: Deploy directly and monitor - fresh start allows
real-world validation
4. Improve_tool Action: Keep current behavior (discard immediately) - no
auto-enhancement

---
Phase 2: Unified Tool Creation/Enhancement Agent

2.1: Update NewToolAnalysis Schema

File: baml_src/schemas.baml (lines 113-118)

Action: Replace the NewToolAnalysis class with:

class NewToolAnalysis {
thoughts string @description("Step-by-step analysis of execution history")

action "create_new" | "enhance_existing" | "none" @description(#"
 - create_new: Create a completely new helper function
 - enhance_existing: Enhance existing tool with optional parameters
 - none: No tool creation or enhancement needed
"#)

tool_name string @description(#"
 For create_new: Name for new function
 For enhance_existing: Name of existing tool to enhance
 For none: Empty string
"#)

tool_description string @description(#"
 For create_new: Full function specification
 For enhance_existing: Enhancement description (what parameters to add)
 For none: Empty string
"#)

existing_tool_for_enhancement string? @description(#"
 Only for enhance_existing: Name of tool to enhance
"#)
}

Key Change: new_tool: bool → action: enum for explicit decision model

---
2.2: Update identify_helper_function.baml

File: baml_src/identify_helper_function.baml

Action 1: Insert enhancement guidance before "YOUR ANALYSIS CRITERIA:"
(after line 25):

 ENHANCEMENT VS CREATION DECISION:

 Before recommending a new tool, check if an existing tool could be
ENHANCED instead.

 **Consider ENHANCEMENT (action="enhance_existing") if:**
 1. Existing tool provides 70%+ of needed functionality
 2. Missing functionality can be added via optional parameters with
sensible defaults
 3. Enhancement maintains backward compatibility (existing code works
unchanged)
 4. Combined tool remains focused and understandable

 **Choose CREATION (action="create_new") if:**
 1. No existing tool provides 70%+ overlap
 2. Pattern is fundamentally different from existing tools
 3. Enhancement would make existing tool too complex
 4. New functionality is orthogonal to existing tools

 **Choose NONE (action="none") if:**
 1. Existing tools already handle this adequately
 2. Pattern is too specific to this question
 3. Direct ifcopenshell calls are clearer

Action 2: Update criteria section (lines 28-45) to mention enhancement:

 A helper function SHOULD be created OR enhanced if:
 1. **Generalizability**: Pattern applies to similar questions
 2. **Abstraction Level**: Higher-level than direct ifcopenshell calls
 3. **Reusability**: Multiple future questions could benefit
 4. **Enhancement Opportunity**: Existing tool is close but missing one
feature
 5. **Clear Interface**: Clear parameters with sensible defaults

Action 3: Add output requirements before {{ ctx.output_format }}:

 OUTPUT REQUIREMENTS:

 1. Set `action` to "create_new", "enhance_existing", or "none"
 2. For "enhance_existing":
    - `tool_name` = existing tool to enhance
    - `tool_description` = what parameters to add
    - `existing_tool_for_enhancement` = same as tool_name
 3. For "create_new":
    - `tool_name` = new function name
    - `tool_description` = full specification
    - `existing_tool_for_enhancement` = null

---
2.3: Unify create_helper_function for Creation AND Enhancement

File: baml_src/create_helper_function.baml

Action 1: Add parameters after line 11:

is_enhancement: bool @description("True if enhancing existing tool"),
existing_implementation: string? @description("Current tool implementation
(empty if new)"),

Action 2: Replace YOUR TASK section (lines 34-50) with conditional logic:

 YOUR TASK:
 {% if is_enhancement %}
 Enhance existing helper function:
 - Name: {{ function_name }}
 - Enhancement: {{ function_description }}
 - Current Implementation:
 ```python
 {{ existing_implementation }}
 ```

 ENHANCEMENT REQUIREMENTS:
 1. Add optional parameters with sensible defaults (backward compatible)
 2. Existing behavior unchanged when new parameters not provided
 3. Extended functionality when new parameters used
 4. Update docstring with new parameters
 5. Test both old usage (without new params) and new usage

 {% else %}
 Create new helper function:
 - Name: {{ function_name }}
 - Description: {{ function_description }}
 {% endif %}

File: src/agents/create_helper_function.py

Action 1: Update _helper_function_creator_iter signature (line 26):

def _helper_function_creator_iter(
 history: str,
 example_question: str,
 example_answer: str,
 example_bim_model: str,
 other_bim_models_for_testing: List[str],
 function_name: str,
 function_description: str,
 is_enhancement: bool = False,
 existing_implementation: Optional[str] = None,
 previous_attempts: Optional[str] = None,
 **kwargs,
) -> CodeAction | NewHelperFunction:

Action 2: Update BAML call (lines 68-92) to pass new parameters:

result = b.with_options(**baml_options).HelperFunctionCreator(
 # ... existing parameters ...
 is_enhancement=is_enhancement,
 existing_implementation=existing_implementation,
 # ... rest ...
)

Action 3: Update public API create_helper_function (line 432):

def create_helper_function(
 history: str,
 example_question: str,
 example_answer: str,
 example_bim_model: str,
 function_name: str,
 function_description: str,
 is_enhancement: bool = False,
 existing_implementation: Optional[str] = None,
 other_bim_models_for_testing: Optional[List[str]] = None,
 max_iterations: int = 15,
 llm_provider: str = "zai",
 llm_name: str = "GLM-4.6",
 **kwargs,
) -> Tuple[NewHelperFunction, Collector, str]:

---
2.4: Update Training State Machine for Enhancement

File: scripts/run_training_phase.py

Action 1: Add field to Context class (line 99):

is_enhancement: bool = False  # Track if current operation is enhancement

Action 2: Update handle_identify_new_tool (lines 589-653) to handle new
action enum:

def handle_identify_new_tool(context: Context) -> Tuple[TrainingState,
Context]:
 """Identify if new tool should be created or existing tool enhanced."""

 # ... existing identification logic ...

 result, collector = identify_helper_function(
     history=full_history,
     example_question=context.qa_pair.question,
     existing_helper_functions=existing_tools_docs,
     llm_provider="zai",
     llm_name="GLM-4.6",
 )

 context.identify_tool_result = result
 context.identify_tool_collector = collector
 context.identify_tool_duration = time.time() - start_time

 # Handle new action field
 if result.action == "create_new":
     _logger.info(f"Creating new tool: {result.tool_name}")
     context.tool_name = result.tool_name
     context.is_enhancement = False
     return TrainingState.CREATE_NEW_TOOL, context

 elif result.action == "enhance_existing":
     _logger.info(f"Enhancing existing tool: {result.tool_name}")
     context.tool_name = result.tool_name
     context.is_enhancement = True
     return TrainingState.CREATE_NEW_TOOL, context

 else:  # "none"
     _logger.info("No tool creation or enhancement needed")
     return TrainingState.END, context

Action 3: Update handle_create_new_tool (lines 656-749) to support
enhancement:

def handle_create_new_tool(context: Context) -> Tuple[TrainingState,
Context]:
 """Create new tool OR enhance existing tool."""

 action_verb = "Enhancing" if context.is_enhancement else "Creating"
 _logger.info(f"{action_verb} tool: {context.tool_name}...")

 # ... existing setup logic ...

 # Get existing implementation if enhancing
 existing_implementation = None
 if context.is_enhancement:
     from src.util import get_function_code
     code_result = get_function_code(context.tool_name)
     if code_result.is_err():
         raise ValueError(f"Could not retrieve tool code:
{code_result.unwrap_err()}")
     existing_implementation = code_result.unwrap()

 # Call unified agent
 result, collector, creation_history = create_helper_function(
     history=full_history,
     example_question=context.qa_pair.question,
     example_answer=context.qa_pair.ground_truth,
     example_bim_model=ifc_model_path,
     other_bim_models_for_testing=other_models,
     function_name=context.identify_tool_result.tool_name,
     function_description=context.identify_tool_result.tool_description,
     is_enhancement=context.is_enhancement,
     existing_implementation=existing_implementation,
     max_iterations=15,
     llm_provider="zai",
     llm_name="GLM-4.6",
 )

 context.create_tool_result = result
 context.create_tool_collector = collector

 if result.success:
     if context.is_enhancement:
         context.tool_updated = True
     else:
         context.tool_created = True
     return TrainingState.TEST_TOOL_WITH_COBBIE, context

---
Phase 3: Usage-Based Tool Deletion

3.1: Deletion Score Calculation

File: src/db/query.py (add after existing tool functions)

Add three functions:

def calculate_deletion_score(
 tool_stats: ToolUsageStats,
 current_question_num: int,
 grace_period: int = 25
) -> float:
 """
 Calculate deletion score (0-100, higher = more deletable).

 Formula combines:
 - Age factor (older = more opportunity to prove value)
 - Call rate (how often used when available)
 - Success rate (contribution to correct answers)
 - Failure penalty (contribution to wrong answers)

 Returns:
     0.0 if within grace period
     100.0 if never used
     <20.0 for high-value tools
     >70.0 for harmful tools
 """
 age = current_question_num - tool_stats.created_at_question
 included = tool_stats.questions_when_included or 0
 called = tool_stats.questions_when_called or 0
 correct = tool_stats.questions_correct_contribution or 0
 wrong = tool_stats.questions_wrong_contribution or 0

 # Grace period protection
 if age < grace_period:
     return 0.0

 # Never included = instant deletion
 if included == 0:
     return 100.0

 # Calculate rates
 call_rate = called / included
 success_rate = correct / called if called > 0 else 0.0
 failure_rate = wrong / called if called > 0 else 0.0

 # Weighted score (0-100)
 age_score = min(age / 100.0, 1.0) * 20
 call_score = (1.0 - call_rate) * 30
 success_score = (1.0 - success_rate) * 25
 failure_score = failure_rate * 25

 return min(age_score + call_score + success_score + failure_score,
100.0)


def get_tools_ranked_by_deletion_score(
 current_question_num: int,
 grace_period: int = 25
) -> List[Tuple[str, float]]:
 """
 Get all tools ranked by deletion score (highest first).

 Returns:
     List of (tool_name, score) tuples, sorted descending
 """
 all_stats = get_all_tool_stats()

 scored_tools = [
     (stats.tool_name, calculate_deletion_score(stats,
current_question_num, grace_period))
     for stats in all_stats
 ]

 scored_tools.sort(key=lambda x: x[1], reverse=True)
 return scored_tools


def delete_tool_from_db(tool_name: str) -> None:
 """Delete tool metadata from database."""
 with Session(db.ENGINE) as session:
     tool_stats = session.get(ToolUsageStats, tool_name)
     if tool_stats:
         session.delete(tool_stats)
         session.commit()

File: src/util/delete_tool.py (NEW FILE)

"""Delete tools from filesystem and database."""

from pathlib import Path

from src.config import CREATED_TOOLS_PATH, LOG_LEVEL
from src.util import get_logger
from src.db.query import delete_tool_from_db

logger = get_logger(name="delete_tool", log_level=LOG_LEVEL)


def delete_tool(tool_name: str) -> bool:
 """
 Delete tool from filesystem and database.

 Returns:
     True if successful, False otherwise
 """
 try:
     # Delete file
     file_path = Path(CREATED_TOOLS_PATH) / f"{tool_name}.py"
     if file_path.exists():
         file_path.unlink()
         logger.info(f"Deleted tool file: {file_path}")

     # Delete metadata
     delete_tool_from_db(tool_name)
     logger.info(f"Deleted tool metadata: {tool_name}")

     return True

 except Exception as e:
     logger.error(f"Error deleting tool {tool_name}: {e}")
     return False

File: src/util/__init__.py (add export)

from .delete_tool import delete_tool

---
3.2: Integrate Deletion Check in Training Loop

File: scripts/run_training_phase.py

Action 1: Add fields to Context class (lines 82-83):

max_tools: int = 32
grace_period: int = 25

Action 2: Update handle_start_state (lines 433-456) to check and delete
before loading tools:

def handle_start_state(context: Context) -> Tuple[TrainingState, Context]:
 """
 Initialize tools for this QA pair.

 Steps:
 1. Check if tool count exceeds MAX_TOOLS
 2. Delete lowest-value tools if necessary
 3. Load remaining tools
 4. Track tool inclusion in database
 """
 from src.db.query import get_tools_ranked_by_deletion_score
 from src.util import delete_tool

 # Check tool count
 current_tools = get_created_tools()

 if len(current_tools) > context.max_tools:
     num_to_delete = len(current_tools) - context.max_tools
     _logger.info(f"Tool count ({len(current_tools)}) exceeds MAX_TOOLS
({context.max_tools})")
     _logger.info(f"Deleting {num_to_delete} lowest-value tools...")

     # Get ranked tools by deletion score
     ranked_tools = get_tools_ranked_by_deletion_score(
         current_question_num=context.global_question_num,
         grace_period=context.grace_period
     )

     # Delete top N by score
     deleted_count = 0
     for tool_name, score in ranked_tools[:num_to_delete]:
         _logger.info(f"  Deleting '{tool_name}' (score={score:.1f})")
         if delete_tool(tool_name):
             deleted_count += 1

     _logger.info(f"Deleted {deleted_count}/{num_to_delete} tools")

     # Log to MLflow
     if mlflow.active_run():
         mlflow.log_metrics({
             f"tools_deleted_at_q{context.global_question_num}":
deleted_count,
             "current_tool_count": len(get_created_tools())
         })

 # Load available tools
 context.tools = get_created_tools()

 # Track tool inclusion
 available_tool_names = list(context.tools.keys())
 increment_tool_inclusion(available_tool_names,
context.global_question_num)

 _logger.info(f"Loaded {len(context.tools)} tools for question
{context.qa_pair.id}")

 return TrainingState.RUN_COBBIE, context

---
Phase 4: Configuration & Integration

4.1: Add CLI Parameters

File: scripts/run_training_phase.py

Action 1: Update argument parser in main() (lines 1278-1286):

parser.add_argument("--start", type=int, default=0, help="Start index")
parser.add_argument("--end", type=int, default=None, help="End index")
parser.add_argument(
 "--continue", dest="continue_run", nargs="?", const=True,
 help="Continue most recent run or specific run ID"
)
parser.add_argument(
 "--max-tools", type=int, default=32,
 help="Maximum number of tools to maintain (default: 32)"
)
parser.add_argument(
 "--grace-period", type=int, default=25,
 help="Questions to protect new tools from deletion (default: 25)"
)

Action 2: Pass parameters to Context (lines 1370-1373):

context = Context(
 qa_pair=qa_pair,
 global_question_num=global_question_num,
 max_tools=args.max_tools,
 grace_period=args.grace_period,
)

Action 3: Log parameters to MLflow (lines 1316-1322):

mlflow.log_params({
 "model_name": "glm-4.6",
 "provider_name": "zai",
 "component": "Training",
 "max_tools": args.max_tools,
 "grace_period": args.grace_period,
})

---
4.2: Initialize Metadata on Training Start

File: src/db/query.py (add new function)

def initialize_tool_metadata(global_question_num: int) -> int:
 """
 Initialize metadata for existing tools without entries.

 Returns:
     Number of tools initialized
 """
 from src.util import get_created_tools

 existing_tools = get_created_tools()
 initialized_count = 0

 with Session(db.ENGINE) as session:
     for tool_name in existing_tools.keys():
         existing_stats = session.get(ToolUsageStats, tool_name)
         if not existing_stats:
             tool_stats = ToolUsageStats(
                 tool_name=tool_name,
                 questions_when_included=0,
                 questions_when_called=0,
                 questions_correct_contribution=0,
                 questions_wrong_contribution=0,
                 created_at_question=global_question_num,
                 last_question_processed=global_question_num,
             )
             session.add(tool_stats)
             initialized_count += 1

     session.commit()

 return initialized_count

File: scripts/run_training_phase.py

Action: Add initialization after mlflow.start_run() (after line 1311):

with mlflow.start_run(run_id=run_id, run_name=run_name):
 # Initialize tool metadata
 from src.db.query import initialize_tool_metadata

 initialized_count = initialize_tool_metadata(args.start)
 if initialized_count > 0:
     _logger.info(f"Initialized metadata for {initialized_count} existing
tools")

 # ... rest of training loop ...

---
4.3: Support --continue Flag Enhancement

File: scripts/run_training_phase.py

Action: Update dataset loading in main() (lines 1287-1295):

# Load dataset
devset, trainset = load_train_dev_split()

# Handle --continue flag
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

end_index = args.end if args.end else len(trainset)
dataset = trainset[args.start : end_index]

---
Testing & Validation

Unit Tests

New File: test/test_tool_deletion.py

"""Test tool deletion scoring."""

import pytest
from src.db.models import ToolUsageStats
from src.db.query import calculate_deletion_score


def test_grace_period_protection():
 """New tools should have score 0."""
 stats = ToolUsageStats(
     tool_name="new_tool",
     created_at_question=100,
     questions_when_included=10,
     questions_when_called=5,
     questions_correct_contribution=5,
 )

 score = calculate_deletion_score(stats, current_question_num=115,
grace_period=25)
 assert score == 0.0


def test_never_used_tool():
 """Never-used tools should have max score."""
 stats = ToolUsageStats(
     tool_name="unused",
     created_at_question=50,
     questions_when_included=0,
     questions_when_called=0,
 )

 score = calculate_deletion_score(stats, current_question_num=200,
grace_period=25)
 assert score == 100.0


def test_high_value_tool():
 """High-usage tools should have low score."""
 stats = ToolUsageStats(
     tool_name="valuable",
     created_at_question=50,
     questions_when_included=100,
     questions_when_called=80,
     questions_correct_contribution=72,
     questions_wrong_contribution=8,
 )

 score = calculate_deletion_score(stats, current_question_num=200,
grace_period=25)
 assert score < 20.0

Integration Testing

Test Sequence:

1. Phase 2 Tests:
- Run training on 3-5 questions
- Verify NewToolAnalysis returns action field
- Test enhancement flow with existing tool
- Confirm backward compatibility
2. Phase 3 Tests:
- Create >32 dummy tools
- Run training with --max-tools=5
- Verify deletion targets low-score tools
- Check grace period protection
3. Phase 4 Tests:
- Test CLI arguments
- Test --continue flag resumption
- Verify MLflow parameter logging

Commands:
# Type checking
uvx ty check scripts/run_training_phase.py
uvx ty check src/agents/create_helper_function.py
uvx ty check src/db/query.py

# Linting
uvx ruff check scripts/run_training_phase.py src/agents/ src/db/

# Unit tests
uv run pytest test/test_tool_deletion.py -v

# Integration test
uv run scripts/run_training_phase.py --start 0 --end 5 --max-tools 10
--grace-period 20

---
Implementation Sequence

Step 1: Phase 2 (Enhancement Support)

1. Update baml_src/schemas.baml - NewToolAnalysis schema
2. Update baml_src/identify_helper_function.baml - enhancement logic
3. Update baml_src/create_helper_function.baml - conditional prompt
4. Update src/agents/create_helper_function.py - function signatures
5. Update scripts/run_training_phase.py - state machine handlers
6. Run type checks and linting
7. Test with 3-5 questions

Step 2: Phase 3 (Deletion Logic)

1. Add deletion functions to src/db/query.py
2. Create src/util/delete_tool.py
3. Update src/util/__init__.py exports
4. Update scripts/run_training_phase.py - deletion check in START state
5. Create test/test_tool_deletion.py
6. Run unit tests
7. Test with >32 tools

Step 3: Phase 4 (Configuration)

1. Update scripts/run_training_phase.py - CLI arguments
2. Add initialize_tool_metadata() to src/db/query.py
3. Update main() - initialization and --continue flag
4. Test all CLI parameters
5. Run full training cycle

---
Critical Files Summary

| File                                   | Changes
 | Phase       |
|----------------------------------------|----------------------------------
----|-------------|
| baml_src/schemas.baml                  | NewToolAnalysis schema (action
enum) | 2.1         |
| baml_src/identify_helper_function.baml | Enhancement decision logic
 | 2.2         |
| baml_src/create_helper_function.baml   | Conditional creation/enhancement
 | 2.3         |
| src/agents/create_helper_function.py   | Enhancement parameters
 | 2.3         |
| scripts/run_training_phase.py          | State machine + deletion + CLI
 | 2.4, 3.2, 4 |
| src/db/query.py                        | Deletion score + initialization
 | 3.1, 4.2    |
| src/util/delete_tool.py                | Tool deletion function (NEW)
 | 3.1         |
| test/test_tool_deletion.py             | Deletion tests (NEW)
 | 3           |

---
Success Criteria

- ✅ Tool count maintained at ≤32 after deletions
- ✅ Enhancement rate >20% (prefers enhancing over creating)
- ✅ Deletion targets low-score tools (score >50)
- ✅ No tool deleted within grace period
- ✅ All type checks pass (ty, pyright)
- ✅ All unit tests pass
- ✅ Training runs successfully with new features
