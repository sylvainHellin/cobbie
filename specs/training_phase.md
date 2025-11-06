# Training Phase Implementation Specification

## 1. Overview

This document specifies the implementation of the training phase for Cobbie's multi-agent system. The training phase orchestrates the creation, updating, and pruning of tools for extracting information from BIM models.

**Key Workflow**: For each QA pair in the training set, run Cobbie to answer the question, verify the answer, and then either identify opportunities for new tools (if correct) or identify faulty tools (if wrong).

---

## 2. Current State Assessment

### Scaffolding in `scripts/run_training_phase.py`

**✅ Good:**
- Has state machine enum (`TrainingState`)
- Has context structure (`Context`)
- Has `process_state` dispatcher pattern
- Has main loop structure

**⚠️ Missing:**
- All state handler functions (only `handle_start_state` stub exists)
- MLflow integration
- Tool loading/reloading logic
- Error handling and metrics tracking
- Complete Context class fields

### Available Agents (All Production-Ready)

| Agent | Module | Purpose | Returns |
|-------|--------|---------|---------|
| `cobbie` | `src.agents.cobbie` | Main BIM Q&A agent | `Tuple[FinalAnswer, Collector, str]` |
| `verify_answer` | `src.agents.answer_verifier` | Answer verification | `Tuple[AnswerEvaluationResult, Collector]` |
| `identify_helper_function` | `src.agents.identify_helper_function` | Identifies new tool opportunities | `Tuple[ToolIdentified, Collector]` |
| `create_helper_function` | `src.agents.create_helper_function` | Creates new tools | `Tuple[NewHelperFunction, Collector, str]` |
| `identify_faulty_tool` | `src.agents.faulty_tool_identifier` | Identifies faulty tools | `Tuple[FaultyToolAnalysis, Collector]` |
| `debug_helper_function` | `src.agents.debug_helper_function` | Fixes faulty tools | `Tuple[ToolFixed, Collector, str]` |

### Available Utility Functions

| Function | Module | Purpose | Returns |
|----------|--------|---------|---------|
| `get_created_tools()` | `src.engine.util.get_created_tools` | Load all created tools dynamically | `Dict[str, Callable]` |
| `save_new_tool()` | `src.engine.util.save_new_tool` | Save tool to disk | `bool` |
| `get_function_code()` | `src.engine.util.get_function_code` | Read tool source code | `Result[str, str]` |
| `generate_tools_docs()` | `src.engine.util.generate_tools_docs` | Generate tool documentation string | `str` |

### Missing Utilities

- **Tool reloading**: No dedicated reload function, but can workaround by calling `get_created_tools()` again
- **Single tool deletion**: `delete_tools()` only deletes exactly 2 tools (not needed for new workflow)

---

## 3. Training Workflow

### State Machine Flow

```
START
  ↓
RUN_COBBIE (Run Cobbie to answer question)
  ↓
VERIFY_ANSWER (Verify if answer is correct)
  ↓
  ├─→ [correct] → IDENTIFY_NEW_TOOL
  │                    ↓
  │                    ├─→ [new_tool=True] → CREATE_NEW_TOOL → END
  │                    └─→ [new_tool=False] → END
  │
  ├─→ [wrong] → IDENTIFY_FAULTY_TOOL
  │                  ↓
  │                  ├─→ [faulty_tool=True] → DEBUG_FAULTY_TOOL → END
  │                  └─→ [faulty_tool=False] → END
  │
  └─→ [abstained] → END (skip both paths)

ERROR (Continue to next QA pair)
END (Move to next QA pair)
```

### Path A: Correct Answer

1. **IDENTIFY_NEW_TOOL**: Call `identify_helper_function()` to analyze execution history
   - Input: Cobbie's execution history, question, existing tools docs
   - Output: `ToolIdentified` with `new_tool` boolean and tool details

2. **CREATE_NEW_TOOL** (if `new_tool == True`):
   - Call `create_helper_function()` to create the tool
   - Input: History, question, answer, **IFC model path from QA pair**, function name/description
   - Output: `NewHelperFunction` with implementation and success status
   - If `success == True`: Save tool with `save_new_tool()`, reload tools
   - If `success == False`: Log error, move to ERROR state

### Path B: Wrong Answer

1. **IDENTIFY_FAULTY_TOOL**: Call `identify_faulty_tool()` to analyze failure
   - Input: History, question, ground truth, provided answer, justification, existing tools
   - Output: `FaultyToolAnalysis` with `faulty_tool` boolean and error details

2. **DEBUG_FAULTY_TOOL** (if `faulty_tool == True`):
   - Get faulty tool source code with `get_function_code()`
   - Call `debug_helper_function()` to fix the tool
   - Input: Faulty function name/implementation, error description, **IFC model path from QA pair**
   - Output: `ToolFixed` with fixed implementation and success status
   - If `success == True`: Save corrected tool with `save_new_tool()`, reload tools
   - If `success == False`: Log error, move to ERROR state

### Future Enhancement: Tool Testing State

**TODO (Not implemented in initial version):**

Add a `TEST_TOOL` state after `CREATE_NEW_TOOL` and `DEBUG_FAULTY_TOOL` that validates the tool before saving it permanently.

**Two possible approaches:**

**Option A: Reuse Cobbie Agent**
- Create a minimal test: "Test if the newly created tool executes without errors on the given IFC model"
- Give Cobbie access ONLY to the new tool
- Expected answer: "OK" if tool works, "ERROR" if it fails
- Pros: Reuses existing infrastructure
- Cons: May be overkill for simple execution testing

**Option B: Dedicated Tool Validator Agent**
- Create a new lightweight agent specifically for tool validation
- Agent would: Load the tool, execute it with test parameters, return pass/fail
- Pros: More focused, potentially simpler
- Cons: Requires creating a new agent

**Recommendation**: Option B (dedicated validator) is cleaner for this specific use case.

---

## 4. Implementation Details

### 4.1 State Machine Enum (Update Required)

```python
class TrainingState(Enum):
    START = auto()
    RUN_COBBIE = auto()
    VERIFY_ANSWER = auto()

    # Path A: Correct answer
    IDENTIFY_NEW_TOOL = auto()
    CREATE_NEW_TOOL = auto()

    # Path B: Wrong answer
    IDENTIFY_FAULTY_TOOL = auto()
    DEBUG_FAULTY_TOOL = auto()

    # Future: Tool testing (not implemented initially)
    # TEST_TOOL = auto()

    # Terminal states
    END = auto()
    ERROR = auto()
```

### 4.2 Context Class (Update Required)

```python
from typing import Dict, Optional, Callable
from pydantic import BaseModel
from baml_py.baml_py import Collector
from baml_client.types import (
    FinalAnswer,
    AnswerEvaluationResult,
    ToolIdentified,
    NewHelperFunction,
    FaultyToolAnalysis,
    ToolFixed,
)
from src.experiment.db.models import IfcBench

class Context(BaseModel):
    # Core data
    qa_pair: IfcBench
    tools: Dict[str, Callable] = {}

    # Cobbie agent results
    cobbie_result: Optional[FinalAnswer] = None
    cobbie_collector: Optional[Collector] = None
    cobbie_history: str = ""
    cobbie_duration: float = 0.0

    # Answer verifier results
    verify_result: Optional[AnswerEvaluationResult] = None
    verify_collector: Optional[Collector] = None
    verify_duration: float = 0.0

    # Identify helper function results (Path A)
    identify_tool_result: Optional[ToolIdentified] = None
    identify_tool_collector: Optional[Collector] = None
    identify_tool_duration: float = 0.0

    # Create helper function results (Path A)
    create_tool_result: Optional[NewHelperFunction] = None
    create_tool_collector: Optional[Collector] = None
    create_tool_history: str = ""
    create_tool_duration: float = 0.0

    # Identify faulty tool results (Path B)
    identify_faulty_result: Optional[FaultyToolAnalysis] = None
    identify_faulty_collector: Optional[Collector] = None
    identify_faulty_duration: float = 0.0

    # Debug helper function results (Path B)
    debug_tool_result: Optional[ToolFixed] = None
    debug_tool_collector: Optional[Collector] = None
    debug_tool_history: str = ""
    debug_tool_duration: float = 0.0

    # Tracking metadata
    error_message: Optional[str] = None
    tool_created: bool = False
    tool_updated: bool = False
    tool_name: Optional[str] = None
    path_taken: Optional[str] = None  # "correct" or "wrong" or "abstained"
```

### 4.3 MLflow Structure

Following the pattern from `scripts/run_evaluation.py`:

#### Main Run
```python
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("Training")

run_name = f"TRAINING_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}_samples_{args.start}_{end_index-1}"

with mlflow.start_run(run_name=run_name) as main_run:
    # Log main-level parameters
    mlflow.log_params({
        "engine_type": "baml",
        "model_name": "glm-4.6",
        "provider_name": "zai",
        "component": "Training",
        "start_index": args.start,
        "end_index": end_index,
        "num_samples": len(trainset),
        "initial_tools_count": len(initial_tools),
    })

    # Process each QA pair...

    # At end: log aggregate metrics
    mlflow.log_metrics({
        "total_qa_pairs": total_count,
        "correct_answers": correct_count,
        "wrong_answers": wrong_count,
        "abstained_answers": abstained_count,
        "tools_created": tools_created_count,
        "tools_updated": tools_updated_count,
        "success_rate": correct_count / total_count,
        "avg_tokens_per_qa": total_tokens / total_count,
        # ... more aggregate metrics
    })
```

#### Nested Run per QA Pair
```python
run_name = f"question_{qa_pair.id}"

with mlflow.start_run(run_name=run_name, nested=True) as qa_run:
    # Log QA-level parameters
    mlflow.log_params({
        "question_id": qa_pair.id,
        "question": qa_pair.question,
        "ground_truth": qa_pair.answer,
        "category": qa_pair.category,
        "ifc_model_path": qa_pair.ifc.model_path if qa_pair.ifc else None,
        "engine_type": "baml",
    })

    # Create span for overall QA processing
    with mlflow.start_span(name="TrainingQA", span_type="CHAIN") as qa_span:
        # Process through state machine...

        # Log QA-level metrics
        mlflow.log_metrics({
            "cobbie_duration": context.cobbie_duration,
            "cobbie_input_tokens": cobbie_input_tokens,
            "cobbie_output_tokens": cobbie_output_tokens,
            "verify_duration": context.verify_duration,
            "verify_input_tokens": verify_input_tokens,
            "verify_output_tokens": verify_output_tokens,
            "total_tokens": total_tokens,
            "answer_correct": 1 if classification == "correct" else 0,
            "tool_created": 1 if context.tool_created else 0,
            "tool_updated": 1 if context.tool_updated else 0,
            # ... more per-QA metrics
        })
```

### 4.4 State Handler Functions

#### `handle_start_state(context: Context) -> Tuple[TrainingState, Context]`

```python
def handle_start_state(context: Context) -> Tuple[TrainingState, Context]:
    """
    Initialize tools for this QA pair.

    Actions:
    1. Load all created tools with get_created_tools()
    2. Store in context
    3. Log initial tool count

    Returns:
        Next state: RUN_COBBIE
    """
    from src.engine.util import get_created_tools

    # Load all available tools
    context.tools = get_created_tools()

    _logger.info(f"Loaded {len(context.tools)} tools for question {context.qa_pair.id}")

    return TrainingState.RUN_COBBIE, context
```

#### `handle_run_cobbie(context: Context) -> Tuple[TrainingState, Context]`

```python
def handle_run_cobbie(context: Context) -> Tuple[TrainingState, Context]:
    """
    Run Cobbie agent to answer the question.

    Actions:
    1. Generate tools documentation
    2. Call cobbie() with tools
    3. Store result, collector, history in context
    4. Log metrics to MLflow span

    Returns:
        Next state: VERIFY_ANSWER
    """
    import time
    from src.agents import cobbie
    from src.engine.util import generate_tools_docs

    # Get IFC model path
    ifc_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

    # Run Cobbie with MLflow span
    with mlflow.start_span(name="Cobbie", span_type="CHAIN") as span:
        start_time = time.time()

        try:
            result, collector, history = cobbie(
                user_input=context.qa_pair.question,
                tools=context.tools,
                max_iterations=10,
                model_path=ifc_path,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.cobbie_result = result
            context.cobbie_collector = collector
            context.cobbie_history = history
            context.cobbie_duration = time.time() - start_time

            # Log to span
            span.set_outputs({
                "answer": result.answer,
                "thoughts": result.thoughts,
                "duration": context.cobbie_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            return TrainingState.VERIFY_ANSWER, context

        except Exception as e:
            _logger.error(f"Error running Cobbie: {e}")
            context.error_message = f"Cobbie error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

#### `handle_verify_answer(context: Context) -> Tuple[TrainingState, Context]`

```python
def handle_verify_answer(context: Context) -> Tuple[TrainingState, Context]:
    """
    Verify if Cobbie's answer is correct.

    Actions:
    1. Call verify_answer() with question, ground truth, system response
    2. Store result in context
    3. Branch based on classification

    Returns:
        Next state:
        - IDENTIFY_NEW_TOOL if classification == "correct"
        - IDENTIFY_FAULTY_TOOL if classification == "wrong"
        - END if classification == "abstained"
    """
    import time
    from src.agents import verify_answer

    with mlflow.start_span(name="AnswerVerifier", span_type="LLM") as span:
        start_time = time.time()

        try:
            result, collector = verify_answer(
                question=context.qa_pair.question,
                category=context.qa_pair.category,
                ground_truth=context.qa_pair.answer,
                system_response=context.cobbie_result.answer,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.verify_result = result
            context.verify_collector = collector
            context.verify_duration = time.time() - start_time

            # Log to span
            span.set_outputs({
                "classification": result.classification,
                "justification": result.justification,
                "confidence": result.confidence,
                "duration": context.verify_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            # Determine next state based on classification
            if result.classification == "correct":
                context.path_taken = "correct"
                _logger.info(f"Answer CORRECT - Following Path A (identify new tool)")
                return TrainingState.IDENTIFY_NEW_TOOL, context
            elif result.classification == "wrong":
                context.path_taken = "wrong"
                _logger.info(f"Answer WRONG - Following Path B (identify faulty tool)")
                return TrainingState.IDENTIFY_FAULTY_TOOL, context
            else:  # "abstained"
                context.path_taken = "abstained"
                _logger.info(f"Answer ABSTAINED - Skipping both paths")
                return TrainingState.END, context

        except Exception as e:
            _logger.error(f"Error verifying answer: {e}")
            context.error_message = f"Answer verification error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

#### `handle_identify_new_tool(context: Context) -> Tuple[TrainingState, Context]` (Path A)

```python
def handle_identify_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Identify if a new helper function should be created (Path A: Correct answer).

    Actions:
    1. Generate existing tools documentation
    2. Call identify_helper_function() with history and question
    3. Store result in context
    4. Decide if tool creation is needed

    Returns:
        Next state:
        - CREATE_NEW_TOOL if new_tool == True
        - END if new_tool == False
    """
    import time
    from src.agents import identify_helper_function
    from src.engine.util import generate_tools_docs

    with mlflow.start_span(name="IdentifyHelperFunction", span_type="LLM") as span:
        start_time = time.time()

        try:
            # Generate existing tools docs
            existing_tools_docs = generate_tools_docs(context.tools)

            # Construct full history with final answer
            full_history = f"{context.cobbie_history}\n\n--- Final Answer ---\nThoughts: {context.cobbie_result.thoughts}\nAnswer: {context.cobbie_result.answer}"

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

            # Log to span
            span.set_outputs({
                "new_tool": result.new_tool,
                "new_tool_name": result.new_tool_name,
                "new_tool_description": result.new_tool_description,
                "thoughts": result.thoughts,
                "duration": context.identify_tool_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            # Decide next state
            if result.new_tool:
                context.tool_name = result.new_tool_name
                _logger.info(f"New tool identified: {result.new_tool_name}")
                return TrainingState.CREATE_NEW_TOOL, context
            else:
                _logger.info("No new tool needed")
                return TrainingState.END, context

        except Exception as e:
            _logger.error(f"Error identifying new tool: {e}")
            context.error_message = f"Identify new tool error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

#### `handle_create_new_tool(context: Context) -> Tuple[TrainingState, Context]` (Path A)

```python
def handle_create_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Create a new helper function (Path A: Correct answer).

    Actions:
    1. Get IFC model path from QA pair (NOT a dummy model)
    2. Get other BIM models for testing
    3. Call create_helper_function()
    4. If success: Save tool, reload tools, mark as created
    5. If failure: Log error

    Returns:
        Next state:
        - END if success
        - ERROR if failure

    TODO: Add TEST_TOOL state before saving to validate the tool executes properly
    """
    import time
    import os
    from src.agents import create_helper_function
    from src.engine.util import save_new_tool, get_created_tools

    with mlflow.start_span(name="CreateHelperFunction", span_type="CHAIN") as span:
        start_time = time.time()

        try:
            # Get IFC model path from the QA pair (same model used for answering)
            ifc_model_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

            if not ifc_model_path:
                raise ValueError("No IFC model path available for tool creation")

            # Get other BIM models for testing (from bim_models directory)
            bim_models_dir = "/Users/sylvainhellin/GitHub/4_phd/cobbie/src/experiment/bim_models"
            other_models = [
                os.path.join(bim_models_dir, f)
                for f in os.listdir(bim_models_dir)
                if f.endswith(".ifc") and os.path.join(bim_models_dir, f) != ifc_model_path
            ][:3]  # Limit to 3 other models

            # Construct full history
            full_history = f"{context.cobbie_history}\n\n--- Final Answer ---\nThoughts: {context.cobbie_result.thoughts}\nAnswer: {context.cobbie_result.answer}"

            result, collector, creation_history = create_helper_function(
                history=full_history,
                example_question=context.qa_pair.question,
                example_answer=context.qa_pair.answer,
                example_bim_model=ifc_model_path,
                other_bim_models_for_testing=other_models,
                function_name=context.identify_tool_result.new_tool_name,
                function_description=context.identify_tool_result.new_tool_description,
                max_iterations=15,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.create_tool_result = result
            context.create_tool_collector = collector
            context.create_tool_history = creation_history
            context.create_tool_duration = time.time() - start_time

            # Log to span
            span.set_outputs({
                "success": result.success,
                "function_name": context.tool_name,
                "function_implementation": result.function_implementation,
                "thoughts": result.thoughts,
                "duration": context.create_tool_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            if result.success:
                # TODO: Add TEST_TOOL state here to validate tool before saving
                # For now, directly save the tool

                # Save the new tool
                save_success = save_new_tool(
                    function_name=context.tool_name,
                    function_implementation=result.function_implementation,
                )

                if save_success:
                    _logger.info(f"New tool created and saved: {context.tool_name}")
                    context.tool_created = True

                    # Reload tools to include the new one
                    context.tools = get_created_tools()
                    _logger.info(f"Tools reloaded. Now have {len(context.tools)} tools")

                    span.set_attributes({"tool_saved": True})
                    return TrainingState.END, context
                else:
                    _logger.error(f"Failed to save new tool: {context.tool_name}")
                    context.error_message = f"Failed to save tool: {context.tool_name}"
                    span.set_status("ERROR")
                    return TrainingState.ERROR, context
            else:
                _logger.warning(f"Tool creation was not successful: {result.thoughts}")
                context.error_message = f"Tool creation failed: {result.thoughts}"
                span.set_status("ERROR")
                return TrainingState.ERROR, context

        except Exception as e:
            _logger.error(f"Error creating new tool: {e}")
            context.error_message = f"Create tool error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

#### `handle_identify_faulty_tool(context: Context) -> Tuple[TrainingState, Context]` (Path B)

```python
def handle_identify_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Identify if a faulty helper function caused the wrong answer (Path B: Wrong answer).

    Actions:
    1. Generate existing tools documentation
    2. Call identify_faulty_tool() with history, answers, and justification
    3. Store result in context
    4. Decide if tool debugging is needed

    Returns:
        Next state:
        - DEBUG_FAULTY_TOOL if faulty_tool == True
        - END if faulty_tool == False
    """
    import time
    from src.agents import identify_faulty_tool
    from src.engine.util import generate_tools_docs

    with mlflow.start_span(name="IdentifyFaultyTool", span_type="LLM") as span:
        start_time = time.time()

        try:
            # Generate existing tools docs
            existing_tools_docs = generate_tools_docs(context.tools)

            # Construct full history with final answer
            full_history = f"{context.cobbie_history}\n\n--- Final Answer ---\nThoughts: {context.cobbie_result.thoughts}\nAnswer: {context.cobbie_result.answer}"

            result, collector = identify_faulty_tool(
                history=full_history,
                question=context.qa_pair.question,
                ground_truth=context.qa_pair.answer,
                provided_answer=context.cobbie_result.answer,
                justification=context.verify_result.justification,
                existing_helper_functions=existing_tools_docs,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.identify_faulty_result = result
            context.identify_faulty_collector = collector
            context.identify_faulty_duration = time.time() - start_time

            # Log to span
            span.set_outputs({
                "faulty_tool": result.faulty_tool,
                "faulty_tool_name": result.faulty_tool_name,
                "error_description": result.error_description,
                "confidence": result.confidence,
                "thoughts": result.thoughts,
                "duration": context.identify_faulty_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            # Decide next state
            if result.faulty_tool:
                context.tool_name = result.faulty_tool_name
                _logger.info(f"Faulty tool identified: {result.faulty_tool_name} (confidence: {result.confidence})")
                return TrainingState.DEBUG_FAULTY_TOOL, context
            else:
                _logger.info("No faulty tool identified - error was due to other reasons")
                return TrainingState.END, context

        except Exception as e:
            _logger.error(f"Error identifying faulty tool: {e}")
            context.error_message = f"Identify faulty tool error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

#### `handle_debug_faulty_tool(context: Context) -> Tuple[TrainingState, Context]` (Path B)

```python
def handle_debug_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Debug and fix a faulty helper function (Path B: Wrong answer).

    Actions:
    1. Get faulty tool source code with get_function_code()
    2. Get IFC model path from QA pair (NOT a dummy model)
    3. Call debug_helper_function()
    4. If success: Save corrected tool, reload tools, mark as updated
    5. If failure: Log error

    Returns:
        Next state:
        - END if success
        - ERROR if failure

    TODO: Add TEST_TOOL state before saving to validate the corrected tool
    """
    import time
    from src.agents import debug_helper_function
    from src.engine.util import get_function_code, save_new_tool, get_created_tools

    with mlflow.start_span(name="DebugHelperFunction", span_type="CHAIN") as span:
        start_time = time.time()

        try:
            # Get the faulty tool's source code
            faulty_code_result = get_function_code(context.tool_name)

            if faulty_code_result.is_err():
                raise ValueError(f"Could not retrieve faulty tool code: {faulty_code_result.unwrap_err()}")

            faulty_implementation = faulty_code_result.unwrap()

            # Get IFC model path from the QA pair (same model used for answering)
            ifc_model_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

            if not ifc_model_path:
                raise ValueError("No IFC model path available for tool debugging")

            # Construct full history
            full_history = f"{context.cobbie_history}\n\n--- Final Answer ---\nThoughts: {context.cobbie_result.thoughts}\nAnswer: {context.cobbie_result.answer}"

            result, collector, debug_history = debug_helper_function(
                faulty_function_name=context.tool_name,
                faulty_function_implementation=faulty_implementation,
                error_description=context.identify_faulty_result.error_description,
                history_faulty_tool_use=full_history,
                ifc_model_path=ifc_model_path,
                max_iterations=15,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.debug_tool_result = result
            context.debug_tool_collector = collector
            context.debug_tool_history = debug_history
            context.debug_tool_duration = time.time() - start_time

            # Log to span
            span.set_outputs({
                "success": result.success,
                "function_name": context.tool_name,
                "fixed_implementation": result.fixed_implementation,
                "changes_summary": result.changes_summary,
                "thoughts": result.thoughts,
                "duration": context.debug_tool_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            if result.success:
                # TODO: Add TEST_TOOL state here to validate corrected tool before saving
                # For now, directly save the corrected tool

                # Save the corrected tool (overwrites the faulty one)
                save_success = save_new_tool(
                    function_name=context.tool_name,
                    function_implementation=result.fixed_implementation,
                )

                if save_success:
                    _logger.info(f"Faulty tool corrected and saved: {context.tool_name}")
                    context.tool_updated = True

                    # Reload tools to include the corrected version
                    context.tools = get_created_tools()
                    _logger.info(f"Tools reloaded. Now have {len(context.tools)} tools")

                    span.set_attributes({"tool_saved": True})
                    return TrainingState.END, context
                else:
                    _logger.error(f"Failed to save corrected tool: {context.tool_name}")
                    context.error_message = f"Failed to save corrected tool: {context.tool_name}"
                    span.set_status("ERROR")
                    return TrainingState.ERROR, context
            else:
                _logger.warning(f"Tool debugging was not successful: {result.thoughts}")
                context.error_message = f"Tool debugging failed: {result.thoughts}"
                span.set_status("ERROR")
                return TrainingState.ERROR, context

        except Exception as e:
            _logger.error(f"Error debugging faulty tool: {e}")
            context.error_message = f"Debug tool error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

### 4.5 Helper Functions

#### `extract_token_metrics(collector: Optional[Collector]) -> Tuple[int, int, int]`

```python
def extract_token_metrics(collector: Optional[Collector]) -> Tuple[int, int, int]:
    """
    Safely extract token metrics from collector.

    Args:
        collector: BAML Collector object with token usage info

    Returns:
        Tuple of (input_tokens, output_tokens, total_tokens)
    """
    if not collector:
        return 0, 0, 0

    try:
        if hasattr(collector, "usage") and collector.usage:
            usage = collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens
            return input_tokens, output_tokens, total_tokens
    except Exception as e:
        _logger.warning(f"Error extracting token usage: {e}")

    return 0, 0, 0
```

#### `calculate_aggregate_metrics(qa_results: List[dict]) -> dict`

```python
def calculate_aggregate_metrics(qa_results: List[dict]) -> dict:
    """
    Calculate aggregate metrics across all QA pairs.

    Args:
        qa_results: List of dictionaries with per-QA metrics

    Returns:
        Dictionary with aggregate metrics
    """
    total_count = len(qa_results)
    correct_count = sum(1 for r in qa_results if r.get("classification") == "correct")
    wrong_count = sum(1 for r in qa_results if r.get("classification") == "wrong")
    abstained_count = sum(1 for r in qa_results if r.get("classification") == "abstained")

    tools_created = sum(1 for r in qa_results if r.get("tool_created"))
    tools_updated = sum(1 for r in qa_results if r.get("tool_updated"))
    errors = sum(1 for r in qa_results if r.get("error"))

    total_tokens = sum(r.get("total_tokens", 0) for r in qa_results)
    total_duration = sum(r.get("total_duration", 0) for r in qa_results)

    return {
        "total_qa_pairs": total_count,
        "correct_answers": correct_count,
        "wrong_answers": wrong_count,
        "abstained_answers": abstained_count,
        "tools_created": tools_created,
        "tools_updated": tools_updated,
        "errors": errors,
        "success_rate": correct_count / total_count if total_count > 0 else 0,
        "tool_creation_rate": tools_created / correct_count if correct_count > 0 else 0,
        "tool_update_rate": tools_updated / wrong_count if wrong_count > 0 else 0,
        "avg_tokens_per_qa": total_tokens / total_count if total_count > 0 else 0,
        "avg_duration_per_qa": total_duration / total_count if total_count > 0 else 0,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
    }
```

### 4.6 Main Loop Structure

```python
def main():
    """Main training loop."""
    import argparse
    from datetime import datetime
    from src.experiment.datasets import load_train_dev_split
    from src.engine.util import get_logger

    # Parse arguments
    parser = argparse.ArgumentParser(description="Run training phase")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--end", type=int, default=None, help="End index")
    args = parser.parse_args()

    # Setup logger
    _logger = get_logger(name="TrainingPhase", log_level="INFO")

    # Load dataset
    devset, trainset = load_train_dev_split()
    end_index = args.end if args.end else len(trainset)
    dataset = trainset[args.start:end_index]

    _logger.info(f"Starting training phase with {len(dataset)} QA pairs")

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Training")

    run_name = f"TRAINING_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}_samples_{args.start}_{end_index-1}"

    # Main MLflow run
    with mlflow.start_run(run_name=run_name) as main_run:
        # Log main-level parameters
        initial_tools = get_created_tools()
        mlflow.log_params({
            "engine_type": "baml",
            "model_name": "glm-4.6",
            "provider_name": "zai",
            "component": "Training",
            "start_index": args.start,
            "end_index": end_index,
            "num_samples": len(dataset),
            "initial_tools_count": len(initial_tools),
        })

        # Track results for aggregate metrics
        qa_results = []

        # Process each QA pair
        for idx, qa_pair in enumerate(dataset):
            _logger.info(f"\n{'='*80}")
            _logger.info(f"Processing QA {idx+1}/{len(dataset)}: {qa_pair.id}")
            _logger.info(f"{'='*80}")

            # Create nested run for this QA pair
            qa_run_name = f"question_{qa_pair.id}"

            with mlflow.start_run(run_name=qa_run_name, nested=True):
                # Log QA-level parameters
                mlflow.log_params({
                    "question_id": qa_pair.id,
                    "question": qa_pair.question,
                    "ground_truth": qa_pair.answer,
                    "category": qa_pair.category,
                    "ifc_model_path": qa_pair.ifc.model_path if qa_pair.ifc else None,
                })

                # Initialize context and state
                context = Context(qa_pair=qa_pair)
                state = TrainingState.START

                # State machine loop
                try:
                    while state not in [TrainingState.END, TrainingState.ERROR]:
                        state, context = process_state(state, context)

                    # Log QA-level metrics
                    qa_result = log_qa_metrics(context)
                    qa_results.append(qa_result)

                    if state == TrainingState.ERROR:
                        _logger.error(f"QA {qa_pair.id} ended with error: {context.error_message}")
                        mlflow.set_tag("status", "error")
                    else:
                        _logger.info(f"QA {qa_pair.id} completed successfully")
                        mlflow.set_tag("status", "success")

                except Exception as e:
                    _logger.error(f"Unexpected error processing QA {qa_pair.id}: {e}")
                    qa_results.append({
                        "question_id": qa_pair.id,
                        "error": True,
                        "error_message": str(e),
                    })
                    mlflow.set_tag("status", "exception")
                    # Continue to next QA pair (per user requirement)

        # Calculate and log aggregate metrics
        aggregate_metrics = calculate_aggregate_metrics(qa_results)
        mlflow.log_metrics(aggregate_metrics)

        _logger.info(f"\n{'='*80}")
        _logger.info("Training Phase Complete")
        _logger.info(f"{'='*80}")
        _logger.info(f"Total QA pairs: {aggregate_metrics['total_qa_pairs']}")
        _logger.info(f"Correct answers: {aggregate_metrics['correct_answers']}")
        _logger.info(f"Wrong answers: {aggregate_metrics['wrong_answers']}")
        _logger.info(f"Abstained: {aggregate_metrics['abstained_answers']}")
        _logger.info(f"Tools created: {aggregate_metrics['tools_created']}")
        _logger.info(f"Tools updated: {aggregate_metrics['tools_updated']}")
        _logger.info(f"Errors: {aggregate_metrics['errors']}")
        _logger.info(f"Success rate: {aggregate_metrics['success_rate']:.2%}")

if __name__ == "__main__":
    main()
```

---

## 5. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tool reloading | Reload after each creation/update via `get_created_tools()` | Ensures newly created/updated tools are immediately available for subsequent QA pairs |
| Tool creation validation | Create immediately when `identify_helper_function` suggests | Trust the agent's judgment; validation can be added later via TEST_TOOL state |
| Abstained answers | Skip both paths (IDENTIFY_NEW_TOOL and IDENTIFY_FAULTY_TOOL) | No clear signal about correctness, so no action is safest |
| Error handling | Log error and continue to next QA pair | Maximize training coverage; don't let one failure stop entire run |
| MLflow structure | Main run + nested runs per QA pair | Follows evaluation script pattern; provides hierarchical tracking |
| Metrics tracking | Token usage, execution time, tool actions, error details, correctness | Comprehensive tracking for analysis and optimization |
| Tool merging | Not included | Removed from new workflow per user specification |
| IFC model for tool creation/debugging | Use same model from QA pair | Ensures tool is created/tested with relevant real-world model |

---

## 6. Future Enhancements

### TEST_TOOL State (TODO)

After creating or debugging a tool, add validation before saving:

```python
class TrainingState(Enum):
    # ... existing states ...
    TEST_TOOL = auto()  # Add this state
```

**Two implementation options:**

**Option A: Reuse Cobbie (Simpler, may be overkill)**
```python
def handle_test_tool(context: Context) -> Tuple[TrainingState, Context]:
    """Test newly created/corrected tool before saving."""
    # Give Cobbie ONLY the new tool
    test_tools = {context.tool_name: context.tools[context.tool_name]}

    # Ask simple question: "Test if the tool executes properly"
    result, _, _ = cobbie(
        user_input=f"Test the {context.tool_name} function with the IFC model",
        tools=test_tools,
        max_iterations=3,
        model_path=context.qa_pair.ifc.model_path,
    )

    # Check if answer is "OK" or contains errors
    if "OK" in result.answer and "ERROR" not in result.answer:
        # Tool passes, save it
        return save_and_reload_tool(context)
    else:
        # Tool fails, don't save
        context.error_message = f"Tool test failed: {result.answer}"
        return TrainingState.ERROR, context
```

**Option B: Dedicated Tool Validator (Recommended)**
```python
def handle_test_tool(context: Context) -> Tuple[TrainingState, Context]:
    """Test newly created/corrected tool with lightweight validator."""
    from src.agents import validate_tool  # New agent

    result, collector = validate_tool(
        function_name=context.tool_name,
        function_implementation=context.create_tool_result.function_implementation,
        ifc_model_path=context.qa_pair.ifc.model_path,
    )

    if result.passes_tests:
        # Tool passes validation, save it
        return save_and_reload_tool(context)
    else:
        # Tool fails validation, don't save
        context.error_message = f"Tool validation failed: {result.error_message}"
        return TrainingState.ERROR, context
```

**Recommendation**: Option B (dedicated validator) is cleaner and more focused for this specific use case.

---

## 7. Files to Modify

### Primary Implementation
- **`scripts/run_training_phase.py`**: Complete implementation of the training loop

### No New Files Needed
All required agents and utilities already exist in:
- `src/agents/` - All agents ready to use
- `src/engine/util/` - All utilities available

---

## 8. Testing Strategy

### Unit Testing
- Test each state handler function independently
- Mock agent responses to test branching logic
- Verify MLflow logging at each level

### Integration Testing
- Test with small dataset (5-10 QA pairs)
- Verify state transitions work correctly
- Ensure tools are created/updated properly
- Check MLflow hierarchy is correct

### End-to-End Testing
- Run on larger dataset (50-100 QA pairs)
- Verify tool persistence across QA pairs
- Check aggregate metrics are accurate
- Monitor for memory leaks or performance issues

---

## 9. Success Criteria

The implementation is successful when:

✅ All QA pairs are processed without crashing
✅ Correct answers trigger tool identification and creation
✅ Wrong answers trigger faulty tool identification and debugging
✅ Abstained answers are skipped gracefully
✅ Tools are saved and reloaded correctly
✅ MLflow hierarchy matches evaluation script pattern
✅ All metrics are logged correctly (per-QA and aggregate)
✅ Errors are handled gracefully (logged but don't stop training)
✅ Final tool count increases appropriately
✅ Aggregate metrics are calculated and logged

---

## 10. References

- **Evaluation Script**: `scripts/run_evaluation.py` - MLflow pattern reference
- **Legacy Training Module**: `src/engine/components/training_module.py` - Old workflow reference
- **Agent Guidelines**: `src/agents/agents_implementation_guideline.md` - Best practices
- **Available Agents**: `src/agents/` - All production-ready agents
- **Utility Functions**: `src/engine/util/` - Helper functions
