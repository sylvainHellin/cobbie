# Helper Function Testing Implementation Specification

## 1. Overview

This document specifies the implementation of helper function testing in Cobbie's training phase. The testing mechanism validates newly created or debugged helper functions by re-running Cobbie with guided prompts and analyzing tool usage patterns.

**Key Workflow**: After creating or debugging a helper function, re-run Cobbie with an enhanced question that encourages using the new tool, then analyze the execution history to determine if the tool was helpful.

---

## 2. Architecture Decision

### Chosen Approach: **Guided Cobbie Re-run + Tool Usage Analysis**

Instead of creating a dedicated black-box testing agent, we:
1. **Re-run Cobbie** with an enhanced question that suggests using the new tool
2. **Analyze tool usage** with a lightweight agent that examines execution history
3. **Make informed decisions** about keeping, discarding, or improving the tool

### Why This Approach?

| Criterion | Score | Justification |
|-----------|-------|---------------|
| **Validation Quality** | ⭐⭐⭐⭐⭐ | Tests tool in real-world usage context |
| **Implementation Simplicity** | ⭐⭐⭐⭐ | Reuses existing Cobbie agent, one new analysis agent |
| **Cost-Effectiveness** | ⭐⭐⭐⭐ | One Cobbie run + lightweight analysis (~$0.06-0.17) |
| **Targeted Feedback** | ⭐⭐⭐⭐⭐ | Specific assessment of the tool's contribution |
| **False Negative Rate** | ⭐⭐⭐⭐⭐ | Enhanced question reduces "tool ignored" cases |

### Alternative Approaches (Not Chosen)

**Option A: Simple Re-run Without Guidance**
- ❌ High false negatives (tool might be ignored)
- ❌ No tool-specific feedback

**Option B: Dedicated Black-box Testing Agent**
- ❌ Higher implementation complexity
- ❌ Artificial testing environment (not real usage)
- ✅ Faster and cheaper

**Option C: Full test_and_improve Integration**
- ❌ Overly complex for initial validation
- ❌ Significantly higher cost
- ✅ Most thorough testing

---

## 3. Components to Implement

### 3.1 Schema Addition (`baml_src/schemas.baml`)

Following the naming pattern (`NewToolAnalysis`, `FaultyToolAnalysis`), we add:

```baml
// Helper function usage assessment - analyzes if a specific tool was helpful during execution
class HelperFunctionAssessment {
  thoughts string @description("Detailed analysis of how the tool was used during execution")
  
  tool_was_used bool @description("Whether the tool was actually called during execution")
  
  tool_usage_quality "helpful" | "not_used" | "ignored" | "misused" | "harmful" @description(#"
    Assessment of how the tool contributed to the answer:
    - helpful: Tool was used correctly and contributed to producing the correct answer
    - not_used: Tool was available but Cobbie didn't use it at all
    - ignored: Tool was considered/mentioned but deemed unnecessary or not applicable
    - misused: Tool was used incorrectly (wrong parameters, wrong context, misunderstood purpose)
    - harmful: Tool was used and led to incorrect results or wrong reasoning
  "#)
  
  usage_details string @description(#"
    Detailed explanation of tool usage patterns and outcomes:
    - If helpful: How the tool contributed to the correct answer
    - If not_used: Why the tool wasn't needed or what alternative approach was used
    - If ignored: Why Cobbie chose not to use it
    - If misused: What parameters were wrong or how the usage was incorrect
    - If harmful: How the tool's output led to the wrong answer
  "#)
  
  recommendation "keep_tool" | "discard_tool" | "improve_tool" | "unclear" @description(#"
    Final recommendation based on usage analysis:
    - keep_tool: Tool was helpful and should be saved permanently
    - discard_tool: Tool wasn't useful, was harmful, or is redundant
    - improve_tool: Tool has potential but needs fixes or refinement
    - unclear: Insufficient evidence to make a confident decision (need more test cases)
  "#)
  
  confidence "high" | "medium" | "low" @description(#"
    Confidence level in this assessment:
    - high: Clear evidence from execution history supports the assessment
    - medium: Strong indicators but some ambiguity or edge cases
    - low: Limited evidence or conflicting signals
  "#)
}
```

**Naming Rationale:**
- Follows pattern: `NewToolAnalysis`, `FaultyToolAnalysis` → `HelperFunctionAssessment`
- More descriptive than `ToolAnalysis` (which could be ambiguous)
- Clearly indicates it's assessing an existing helper function's usage

---

### 3.2 BAML Function (`baml_src/assess_helper_function.baml`)

```baml
// HelperFunctionAssessor - Analyzes execution history to determine if a specific helper function was useful
// This agent examines how a newly created or debugged tool was used (or not used) during Cobbie's execution
// to provide targeted feedback for deciding whether to keep, discard, or improve the tool

function HelperFunctionAssessor(
  execution_history: string @description("Complete execution history from Cobbie: thoughts, code, results, and final answer"),
  original_question: string @description("The original question (without enhancement) that was being answered"),
  ground_truth_answer: string @description("The correct/expected answer to the question"),
  tested_tool_name: string @description("Name of the helper function being assessed"),
  tested_tool_description: string @description("Description of what the helper function is supposed to do"),
  final_answer: string @description("The final answer provided by Cobbie after using (or not using) the tool"),
  answer_correctness: "correct" | "wrong" | "abstained" @description("Classification of the final answer from answer verifier")
) -> HelperFunctionAssessment {
  client GLM_4_6
  prompt #"
    You are an expert Python developer and software architect specializing in BIM (Building Information Modeling) systems.

    Your task is to analyze a Cobbie execution to determine if a specific helper function was useful and should be kept in the tool library.

    CONTEXT:

    We recently created or debugged a helper function and want to assess its value by examining how Cobbie used it (or didn't use it) when answering a question.

    TESTED HELPER FUNCTION:
    Name: {{ tested_tool_name }}
    Description: {{ tested_tool_description }}

    QUESTION & ANSWER:
    Original Question: {{ original_question }}
    Ground Truth (Correct Answer): {{ ground_truth_answer }}
    Cobbie's Final Answer: {{ final_answer }}
    Answer Correctness: {{ answer_correctness }}

    EXECUTION HISTORY:
    {{ execution_history }}

    YOUR ANALYSIS TASK:

    Examine the execution history and determine:

    1. **Was the tool used?**
       - Check if {{ tested_tool_name }} appears in any code blocks
       - Look for function calls to {{ tested_tool_name }}
       - Note if the tool was mentioned in thoughts but not actually called

    2. **How was the tool used?** (if at all)
       - What parameters were passed?
       - Were the parameters correct and appropriate?
       - What did the tool return?
       - How did Cobbie use the tool's output?

    3. **Did the tool contribute to the answer?**
       - Compare tool outputs with the ground truth answer
       - Trace how tool results flowed through subsequent code
       - Determine if the tool helped reach the correct answer

    4. **What is the tool's quality assessment?**
       - helpful: Tool was used correctly and contributed to correctness
       - not_used: Tool was available but never called
       - ignored: Tool was mentioned/considered but explicitly not used
       - misused: Tool was called incorrectly (wrong params, wrong context)
       - harmful: Tool was used and led to incorrect results

    IMPORTANT GUIDELINES:

    - **Focus on this specific tool only** - Ignore other tools' performance
    - **Be evidence-based** - Base your assessment on what actually happened in the execution
    - **Consider the context** - A tool not being used might be okay if it wasn't needed
    - **Trace causality** - If the answer is wrong, determine if this tool caused it
    - **Distinguish misuse from bugs** - Cobbie using it wrong vs tool having a bug

    RECOMMENDATION LOGIC:

    - **keep_tool** if:
      - Tool was used correctly and helped produce correct answer
      - Tool was not used this time but seems generally useful (not applicable to this specific question)
    
    - **discard_tool** if:
      - Tool was used and produced harmful results
      - Tool was not used because a better approach exists
      - Tool is redundant with existing tools
      - Tool is too specific and unlikely to be useful elsewhere
    
    - **improve_tool** if:
      - Tool was misused but seems to have potential with better interface/docs
      - Tool was used but produced incorrect results (bug in implementation)
      - Tool concept is good but needs refinement
    
    - **unclear** if:
      - Tool wasn't used and it's ambiguous whether it should have been
      - Mixed signals (some helpful aspects, some harmful)
      - Need more test cases to determine value

    CONFIDENCE ASSIGNMENT:

    - **high**: Clear, unambiguous evidence supports the assessment
    - **medium**: Strong indicators but some uncertainty or edge cases
    - **low**: Limited evidence, conflicting signals, or highly context-dependent

    {{ ctx.output_format }}
  "#
}

// Test case 1: Tool was helpful and used correctly
test HelperFunctionAssessorHelpfulTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "How many doors are on the ground floor?"
    ground_truth_answer "There are 6 doors on the ground floor."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "There are 6 doors on the ground floor."
    answer_correctness "correct"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I should use the new get_elements_by_building_storey function to find doors by floor.

      Code:
      doors_by_floor = get_elements_by_building_storey(path_ifc_model, 'IfcDoor')
      print(f"Doors by floor: {list(doors_by_floor.keys())}")

      Result:
      Doors by floor: ['Ground Floor', 'First Floor', 'Second Floor']

      --- Iteration 2 ---
      Thoughts: Now I can count the doors on the ground floor.

      Code:
      ground_floor_doors = doors_by_floor.get('Ground Floor', [])
      print(f"Ground floor doors: {len(ground_floor_doors)}")

      Result:
      Ground floor doors: 6

      --- Final Answer ---
      Thoughts: Successfully used the get_elements_by_building_storey function to find and count doors on the ground floor.
      Answer: There are 6 doors on the ground floor.
    "#
  }
}

// Test case 2: Tool was not used but alternative approach worked
test HelperFunctionAssessorNotUsedTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "What is the total floor area of the building?"
    ground_truth_answer "The total floor area is 450 square meters."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "The total floor area is 450 square meters."
    answer_correctness "correct"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I need to calculate total floor area. I'll get all IfcSlab elements and sum their areas.

      Code:
      import ifcopenshell
      import ifcopenshell.util.element as util
      model = ifcopenshell.open(path_ifc_model)
      slabs = model.by_type('IfcSlab')
      total_area = sum(util.get_psets(slab).get('Qto_SlabBaseQuantities', {}).get('GrossArea', 0) for slab in slabs)
      print(f"Total floor area: {total_area}")

      Result:
      Total floor area: 450

      --- Final Answer ---
      Thoughts: Calculated total floor area by summing slab areas.
      Answer: The total floor area is 450 square meters.
    "#
  }
}

// Test case 3: Tool was misused (wrong parameters)
test HelperFunctionAssessorMisusedTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "How many windows are on the first floor?"
    ground_truth_answer "There are 8 windows on the first floor."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "There are 0 windows on the first floor."
    answer_correctness "wrong"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I'll use the new function to get windows by floor. I think I should pass the floor name as a parameter.

      Code:
      first_floor_windows = get_elements_by_building_storey(path_ifc_model, 'First Floor')
      print(f"Windows: {first_floor_windows}")

      Result:
      Error: get_elements_by_building_storey() takes 2 positional arguments but 2 were given. Expected (ifc_file_path, element_type), got (ifc_file_path, 'First Floor')

      --- Iteration 2 ---
      Thoughts: I got an error. Let me try a different approach.

      Code:
      import ifcopenshell
      model = ifcopenshell.open(path_ifc_model)
      windows = model.by_type('IfcWindow')
      # I don't know how to filter by floor now
      print(f"Total windows: {len(windows)}")

      Result:
      Total windows: 24

      --- Final Answer ---
      Thoughts: I couldn't figure out how to filter by floor, giving up.
      Answer: There are 0 windows on the first floor.
    "#
  }
}

// Test case 4: Tool was harmful (returned wrong data)
test HelperFunctionAssessorHarmfulTest {
  functions [HelperFunctionAssessor]
  args {
    original_question "How many doors are on the ground floor?"
    ground_truth_answer "There are 6 doors on the ground floor."
    tested_tool_name "get_elements_by_building_storey"
    tested_tool_description "Get IFC elements grouped by their containing IfcBuildingStorey. Returns a dictionary mapping floor names to lists of elements."
    final_answer "There are 12 doors on the ground floor."
    answer_correctness "wrong"
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I'll use get_elements_by_building_storey to find doors by floor.

      Code:
      doors_by_floor = get_elements_by_building_storey(path_ifc_model, 'IfcDoor')
      ground_floor_doors = doors_by_floor.get('Ground Floor', [])
      print(f"Ground floor doors: {len(ground_floor_doors)}")

      Result:
      Ground floor doors: 12

      --- Final Answer ---
      Thoughts: The function returned 12 doors on the ground floor.
      Answer: There are 12 doors on the ground floor.
    "#
  }
}
```

---

### 3.3 Python Agent (`src/agents/assess_helper_function.py`)

Create a new agent following the established pattern from `identify_helper_function.py` and `faulty_tool_identifier.py`:

```python
"""
Agent that assesses helper function usage.
Analyzes Cobbie execution history to determine if a specific helper function was useful.
"""

import time
from typing import Tuple

import mlflow
from baml_py.baml_py import Collector
from baml_client import b
from baml_client.types import HelperFunctionAssessment
from src.config import LOG_LEVEL
from src.engine.util import get_logger

# Initialize logger
_logger = get_logger(name="baml_helper_function_assessor", log_level=LOG_LEVEL)


def assess_helper_function(
    execution_history: str,
    original_question: str,
    ground_truth_answer: str,
    tested_tool_name: str,
    tested_tool_description: str,
    final_answer: str,
    answer_correctness: str,
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[HelperFunctionAssessment, Collector]:
    """
    Assess whether a specific helper function was useful during execution.

    Similar to identify_faulty_tool but focuses on tool utility rather than faults.
    Analyzes execution history to determine if a newly created or debugged tool
    should be kept, discarded, or improved.

    Args:
        execution_history: Complete execution history from Cobbie (thoughts, code, results, final answer)
        original_question: The original question (without enhancement) that was being answered
        ground_truth_answer: The correct/expected answer to the question
        tested_tool_name: Name of the helper function being assessed
        tested_tool_description: Description of what the helper function is supposed to do
        final_answer: The final answer provided by Cobbie
        answer_correctness: Classification from answer verifier ("correct", "wrong", or "abstained")
        llm_provider: LLM provider name for logging (default: "zai")
        llm_name: LLM model name for logging (default: "GLM-4.6")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (HelperFunctionAssessment, Collector) where HelperFunctionAssessment contains:
        - thoughts: Detailed analysis of tool usage
        - tool_was_used: Whether the tool was actually called
        - tool_usage_quality: helpful | not_used | ignored | misused | harmful
        - usage_details: Detailed explanation of usage patterns
        - recommendation: keep_tool | discard_tool | improve_tool | unclear
        - confidence: high | medium | low
    """
    # Start timer
    start = time.time()

    # Create collector for token tracking
    collector = Collector(name="HelperFunctionAssessor")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    with mlflow.start_span(
        name="HelperFunctionAssessor", span_type="LLM"
    ) as assessor_span:
        assessor_span.set_inputs(
            {
                "original_question": original_question,
                "tested_tool_name": tested_tool_name,
                "tested_tool_description": tested_tool_description,
                "answer_correctness": answer_correctness,
            }
        )

        # Assess helper function usage
        try:
            assessment = b.with_options(
                **kwargs.pop("baml_options", {})
            ).HelperFunctionAssessor(
                execution_history=execution_history,
                original_question=original_question,
                ground_truth_answer=ground_truth_answer,
                tested_tool_name=tested_tool_name,
                tested_tool_description=tested_tool_description,
                final_answer=final_answer,
                answer_correctness=answer_correctness,
                **kwargs,
            )
        except Exception as e:
            _logger.error(f"Error assessing helper function: {e}")
            assessment = HelperFunctionAssessment(
                thoughts=f"An Exception occurred when trying to assess helper function. Exception:\n{e}",
                tool_was_used=False,
                tool_usage_quality="not_used",
                usage_details="Error occurred during assessment",
                recommendation="unclear",
                confidence="low",
            )

        # Log outputs
        assessor_span.set_outputs(
            {
                "thoughts": assessment.thoughts,
                "tool_was_used": assessment.tool_was_used,
                "tool_usage_quality": assessment.tool_usage_quality,
                "recommendation": assessment.recommendation,
                "confidence": assessment.confidence,
            }
        )

        # Calculate metrics
        duration = time.time() - start
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0

        if collector and hasattr(collector, "usage") and collector.usage:
            usage = collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens

        # Set span attributes
        assessor_span.set_attributes(
            {
                "llm.provider": llm_provider,
                "llm.model": llm_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency": duration,
            }
        )

        _logger.info(
            f"Helper function assessment completed. Recommendation: {assessment.recommendation}, "
            f"Confidence: {assessment.confidence}, Tokens: {total_tokens}, Duration: {duration:.2f}s"
        )

        return assessment, collector


# Export for use in other modules
__all__ = ["assess_helper_function"]
```

---

### 3.4 Update Agent Exports (`src/agents/__init__.py`)

Add the new agent to the exports:

```python
from src.agents.assess_helper_function import assess_helper_function

__all__ = [
    # ... existing exports ...
    "assess_helper_function",
]
```

---

### 3.5 State Machine Updates (`scripts/run_training_phase.py`)

#### 3.5.1 Update `TrainingState` Enum

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

    # Tool testing (both paths)
    TEST_TOOL_WITH_COBBIE = auto()
    ASSESS_TOOL_USAGE = auto()
    DECIDE_TOOL_FATE = auto()

    # Terminal states
    END = auto()
    ERROR = auto()
```

#### 3.5.2 Update `Context` Class

```python
class Context(BaseModel):
    # Core data
    qa_pair: IfcBench
    tools: Dict[str, Callable] = {}

    # Cobbie agent results (original run)
    cobbie_result: Optional[FinalAnswer] = None
    cobbie_collector: Optional[Collector] = None
    cobbie_history: str = ""
    cobbie_duration: float = 0.0

    # Answer verifier results (original run)
    verify_result: Optional[AnswerEvaluationResult] = None
    verify_collector: Optional[Collector] = None
    verify_duration: float = 0.0

    # Identify helper function results (Path A)
    identify_tool_result: Optional[NewToolAnalysis] = None
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
    debug_tool_result: Optional[UpdatedHelperFunction] = None
    debug_tool_collector: Optional[Collector] = None
    debug_tool_history: str = ""
    debug_tool_duration: float = 0.0

    # Tool testing results (both paths)
    test_cobbie_result: Optional[FinalAnswer] = None
    test_cobbie_collector: Optional[Collector] = None
    test_cobbie_history: str = ""
    test_cobbie_duration: float = 0.0
    test_verify_result: Optional[AnswerEvaluationResult] = None
    test_verify_collector: Optional[Collector] = None
    test_verify_duration: float = 0.0

    # Tool assessment results (both paths)
    tool_assessment: Optional[HelperFunctionAssessment] = None
    tool_assessment_collector: Optional[Collector] = None
    tool_assessment_duration: float = 0.0

    # Tracking metadata
    error_message: Optional[str] = None
    tool_created: bool = False
    tool_updated: bool = False
    tool_saved: bool = False
    tool_name: Optional[str] = None
    path_taken: Optional[str] = None  # "correct" or "wrong" or "abstained"
```

#### 3.5.3 Update State Handler Flow

**Path A Flow (Correct Answer):**
```python
IDENTIFY_NEW_TOOL → CREATE_NEW_TOOL 
  → TEST_TOOL_WITH_COBBIE → ASSESS_TOOL_USAGE → DECIDE_TOOL_FATE → END
```

**Path B Flow (Wrong Answer):**
```python
IDENTIFY_FAULTY_TOOL → DEBUG_FAULTY_TOOL 
  → TEST_TOOL_WITH_COBBIE → ASSESS_TOOL_USAGE → DECIDE_TOOL_FATE → END
```

#### 3.5.4 Modify Existing State Handlers

**Update `handle_create_new_tool()`:**

```python
def handle_create_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Create a new helper function (Path A: Correct answer).
    
    CHANGED: No longer saves the tool immediately.
    Instead, transitions to TEST_TOOL_WITH_COBBIE for validation.
    """
    # ... existing code to create the tool ...
    
    if result.success:
        # Store the implementation but DON'T save to disk yet
        context.create_tool_result = result
        context.tool_created = True  # Mark as created (pending validation)
        
        _logger.info(f"Tool '{context.tool_name}' created successfully, proceeding to testing")
        
        # Transition to testing instead of saving immediately
        return TrainingState.TEST_TOOL_WITH_COBBIE, context
    else:
        # Creation failed
        _logger.warning(f"Tool creation was not successful: {result.thoughts}")
        context.error_message = f"Tool creation failed: {result.thoughts}"
        span.set_status("ERROR")
        return TrainingState.ERROR, context
```

**Update `handle_debug_faulty_tool()`:**

```python
def handle_debug_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Debug and fix a faulty helper function (Path B: Wrong answer).
    
    CHANGED: No longer saves the tool immediately.
    Instead, transitions to TEST_TOOL_WITH_COBBIE for validation.
    """
    # ... existing code to debug the tool ...
    
    if result.success:
        # Store the fixed implementation but DON'T save to disk yet
        context.debug_tool_result = result
        context.tool_updated = True  # Mark as updated (pending validation)
        
        _logger.info(f"Tool '{context.tool_name}' debugged successfully, proceeding to testing")
        
        # Transition to testing instead of saving immediately
        return TrainingState.TEST_TOOL_WITH_COBBIE, context
    else:
        # Debugging failed
        _logger.warning(f"Tool debugging was not successful: {result.thoughts}")
        context.error_message = f"Tool debugging failed: {result.thoughts}"
        span.set_status("ERROR")
        return TrainingState.ERROR, context
```

#### 3.5.5 New State Handlers

**`handle_test_tool_with_cobbie()`:**

```python
def handle_test_tool_with_cobbie(context: Context) -> Tuple[TrainingState, Context]:
    """
    Re-run Cobbie with enhanced question to test the new/updated tool.

    Actions:
    1. Temporarily add the new/updated tool to the tools dictionary
    2. Enhance the question to encourage using the tool
    3. Run Cobbie with the enhanced question
    4. Store test results in context
    5. Transition to assessment

    Returns:
        Next state: ASSESS_TOOL_USAGE
    """
    import time
    from src.agents import cobbie

    with mlflow.start_span(name="TestToolWithCobbie", span_type="CHAIN") as span:
        start_time = time.time()

        try:
            # Get the tool implementation
            if context.create_tool_result:
                tool_implementation = context.create_tool_result.function_implementation
                _logger.info(f"Testing newly created tool: {context.tool_name}")
            elif context.debug_tool_result:
                tool_implementation = context.debug_tool_result.fixed_implementation
                _logger.info(f"Testing debugged tool: {context.tool_name}")
            else:
                raise ValueError("No tool implementation available for testing")

            # Temporarily add the tool to the tools dictionary
            from src.engine.util import _create_function_from_source_code
            
            creation_result = _create_function_from_source_code(
                function_name=context.tool_name,
                code=tool_implementation,
            )
            
            if creation_result.is_err():
                error_msg = f"Failed to create function for testing: {creation_result.unwrap_err()}"
                _logger.error(error_msg)
                context.error_message = error_msg
                span.set_status("ERROR")
                return TrainingState.ERROR, context
            
            new_tool = creation_result.unwrap()
            
            # Create a copy of tools with the new tool added
            test_tools = context.tools.copy()
            test_tools[context.tool_name] = new_tool
            
            _logger.info(f"Tool '{context.tool_name}' added to test environment. Total tools: {len(test_tools)}")

            # Enhance the question to guide tool usage
            enhanced_question = (
                f"{context.qa_pair.question}\n\n"
                f"NOTE: A helper function `{context.tool_name}` was recently created. "
                f"If it seems relevant, consider using it to help answer this question."
            )

            # Get IFC model path
            ifc_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

            # Run Cobbie with enhanced question and test tools
            result, collector, history = cobbie(
                user_input=enhanced_question,
                tools=test_tools,
                max_iterations=10,
                model_path=ifc_path,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.test_cobbie_result = result
            context.test_cobbie_collector = collector
            context.test_cobbie_history = history
            context.test_cobbie_duration = time.time() - start_time

            # Log to span
            span.set_outputs({
                "answer": result.answer,
                "thoughts": result.thoughts,
                "duration": context.test_cobbie_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            _logger.info(f"Tool testing Cobbie run completed: {result.answer[:100]}...")
            return TrainingState.ASSESS_TOOL_USAGE, context

        except Exception as e:
            _logger.error(f"Error testing tool with Cobbie: {e}")
            context.error_message = f"Tool testing error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

**`handle_assess_tool_usage()`:**

```python
def handle_assess_tool_usage(context: Context) -> Tuple[TrainingState, Context]:
    """
    Analyze if the tested tool was helpful during Cobbie's execution.

    Actions:
    1. Verify the test answer with verify_answer agent
    2. Get tool description from creation/debugging context
    3. Call assess_helper_function to analyze tool usage
    4. Store assessment in context
    5. Transition to decision state

    Returns:
        Next state: DECIDE_TOOL_FATE
    """
    import time
    from src.agents import verify_answer, assess_helper_function

    with mlflow.start_span(name="AssessToolUsage", span_type="CHAIN") as span:
        start_time = time.time()

        try:
            # Verify the test answer
            verify_start = time.time()
            verify_result, verify_collector = verify_answer(
                question=context.qa_pair.question,
                category=context.qa_pair.category,
                ground_truth=context.qa_pair.answer,
                system_response=context.test_cobbie_result.answer,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )
            context.test_verify_result = verify_result
            context.test_verify_collector = verify_collector
            context.test_verify_duration = time.time() - verify_start

            _logger.info(f"Test answer verified: {verify_result.classification} (confidence: {verify_result.confidence})")

            # Get tool description based on path
            if context.create_tool_result:
                tool_description = context.identify_tool_result.new_tool_description
            elif context.debug_tool_result:
                tool_description = context.identify_faulty_result.error_description
            else:
                raise ValueError("No tool context available for assessment")

            # Construct full test history with final answer
            full_test_history = (
                f"{context.test_cobbie_history}\n\n"
                f"--- Final Answer ---\n"
                f"Thoughts: {context.test_cobbie_result.thoughts}\n"
                f"Answer: {context.test_cobbie_result.answer}"
            )

            # Assess tool usage
            assess_start = time.time()
            assessment, assessment_collector = assess_helper_function(
                execution_history=full_test_history,
                original_question=context.qa_pair.question,
                ground_truth_answer=context.qa_pair.answer,
                tested_tool_name=context.tool_name,
                tested_tool_description=tool_description,
                final_answer=context.test_cobbie_result.answer,
                answer_correctness=verify_result.classification,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )
            context.tool_assessment = assessment
            context.tool_assessment_collector = assessment_collector
            context.tool_assessment_duration = time.time() - assess_start

            # Log to span
            span.set_outputs({
                "tool_was_used": assessment.tool_was_used,
                "tool_usage_quality": assessment.tool_usage_quality,
                "recommendation": assessment.recommendation,
                "confidence": assessment.confidence,
            })

            # Extract and log token metrics
            verify_input, verify_output, verify_total = extract_token_metrics(verify_collector)
            assess_input, assess_output, assess_total = extract_token_metrics(assessment_collector)
            
            span.set_attributes({
                "verify_input_tokens": verify_input,
                "verify_output_tokens": verify_output,
                "verify_total_tokens": verify_total,
                "assess_input_tokens": assess_input,
                "assess_output_tokens": assess_output,
                "assess_total_tokens": assess_total,
            })

            _logger.info(
                f"Tool assessment completed: {assessment.recommendation} "
                f"(quality: {assessment.tool_usage_quality}, confidence: {assessment.confidence})"
            )

            return TrainingState.DECIDE_TOOL_FATE, context

        except Exception as e:
            _logger.error(f"Error assessing tool usage: {e}")
            context.error_message = f"Tool assessment error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

**`handle_decide_tool_fate()`:**

```python
def handle_decide_tool_fate(context: Context) -> Tuple[TrainingState, Context]:
    """
    Decide whether to keep, discard, or flag the tool based on assessment.

    Actions:
    1. Examine the assessment recommendation
    2. Make final decision on tool fate
    3. Save tool if recommended (keep_tool)
    4. Log decision and rationale
    5. Update context metadata

    Returns:
        Next state: END
    """
    from src.engine.util import save_new_tool, get_created_tools

    with mlflow.start_span(name="DecideToolFate", span_type="CHAIN") as span:
        try:
            assessment = context.tool_assessment

            # Get tool implementation
            if context.create_tool_result:
                tool_implementation = context.create_tool_result.function_implementation
                action = "created"
            elif context.debug_tool_result:
                tool_implementation = context.debug_tool_result.fixed_implementation
                action = "debugged"
            else:
                raise ValueError("No tool implementation available")

            span.set_inputs({
                "tool_name": context.tool_name,
                "recommendation": assessment.recommendation,
                "confidence": assessment.confidence,
                "tool_usage_quality": assessment.tool_usage_quality,
                "action": action,
            })

            # Decision logic based on recommendation
            if assessment.recommendation == "keep_tool":
                # Tool is helpful, save it permanently
                save_success = save_new_tool(
                    function_name=context.tool_name,
                    function_implementation=tool_implementation,
                )

                if save_success:
                    context.tool_saved = True
                    _logger.info(
                        f"✅ Tool '{context.tool_name}' validated and saved permanently\n"
                        f"   Quality: {assessment.tool_usage_quality}\n"
                        f"   Confidence: {assessment.confidence}\n"
                        f"   Details: {assessment.usage_details[:200]}..."
                    )

                    # Reload tools to include the new one
                    context.tools = get_created_tools()
                    _logger.info(f"Tools reloaded. Now have {len(context.tools)} tools")

                    span.set_outputs({
                        "decision": "saved",
                        "tool_saved": True,
                        "reason": assessment.usage_details,
                    })
                else:
                    _logger.error(f"Failed to save tool: {context.tool_name}")
                    context.error_message = f"Failed to save tool: {context.tool_name}"
                    span.set_status("ERROR")
                    return TrainingState.ERROR, context

            elif assessment.recommendation == "discard_tool":
                # Tool is not useful or harmful, discard it
                context.tool_saved = False
                _logger.info(
                    f"❌ Tool '{context.tool_name}' discarded\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Reason: {assessment.usage_details[:200]}..."
                )

                span.set_outputs({
                    "decision": "discarded",
                    "tool_saved": False,
                    "reason": assessment.usage_details,
                })

            elif assessment.recommendation == "improve_tool":
                # Tool has potential but needs work
                context.tool_saved = False
                _logger.info(
                    f"⚠️  Tool '{context.tool_name}' needs improvement (not saved)\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Issues: {assessment.usage_details[:200]}..."
                )

                # Log for potential future retry
                mlflow.log_param(f"tool_{context.tool_name}_needs_improvement", True)

                span.set_outputs({
                    "decision": "needs_improvement",
                    "tool_saved": False,
                    "reason": assessment.usage_details,
                })

            else:  # unclear
                # Conservative: keep it tentatively with low confidence
                save_success = save_new_tool(
                    function_name=context.tool_name,
                    function_implementation=tool_implementation,
                )

                if save_success:
                    context.tool_saved = True
                    _logger.info(
                        f"❓ Tool '{context.tool_name}' assessment unclear, saved tentatively\n"
                        f"   Quality: {assessment.tool_usage_quality}\n"
                        f"   Confidence: {assessment.confidence}\n"
                        f"   Note: {assessment.usage_details[:200]}..."
                    )

                    # Reload tools
                    context.tools = get_created_tools()

                    # Tag for review
                    mlflow.log_param(f"tool_{context.tool_name}_unclear_assessment", True)

                    span.set_outputs({
                        "decision": "saved_tentatively",
                        "tool_saved": True,
                        "reason": "Unclear assessment - keeping conservatively",
                    })
                else:
                    _logger.error(f"Failed to save tool: {context.tool_name}")
                    context.error_message = f"Failed to save tool: {context.tool_name}"
                    span.set_status("ERROR")
                    return TrainingState.ERROR, context

            span.set_status("OK")
            return TrainingState.END, context

        except Exception as e:
            _logger.error(f"Error deciding tool fate: {e}")
            context.error_message = f"Tool fate decision error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

#### 3.5.6 Update `process_state()` Dispatcher

```python
def process_state(state: TrainingState, context: Context) -> Tuple[TrainingState, Context]:
    """Process a single state in the training state machine."""
    
    handlers = {
        TrainingState.START: handle_start_state,
        TrainingState.RUN_COBBIE: handle_run_cobbie,
        TrainingState.VERIFY_ANSWER: handle_verify_answer,
        TrainingState.IDENTIFY_NEW_TOOL: handle_identify_new_tool,
        TrainingState.CREATE_NEW_TOOL: handle_create_new_tool,
        TrainingState.IDENTIFY_FAULTY_TOOL: handle_identify_faulty_tool,
        TrainingState.DEBUG_FAULTY_TOOL: handle_debug_faulty_tool,
        TrainingState.TEST_TOOL_WITH_COBBIE: handle_test_tool_with_cobbie,
        TrainingState.ASSESS_TOOL_USAGE: handle_assess_tool_usage,
        TrainingState.DECIDE_TOOL_FATE: handle_decide_tool_fate,
    }
    
    handler = handlers.get(state)
    if handler:
        return handler(context)
    else:
        _logger.error(f"No handler for state: {state}")
        return TrainingState.ERROR, context
```

#### 3.5.7 Update Metrics Logging

**Update `log_qa_metrics()` function:**

```python
def log_qa_metrics(context: Context) -> dict:
    """Extract and log metrics for a single QA pair to MLflow."""
    
    # Extract token metrics from all collectors
    cobbie_input, cobbie_output, cobbie_total = extract_token_metrics(context.cobbie_collector)
    verify_input, verify_output, verify_total = extract_token_metrics(context.verify_collector)
    identify_tool_input, identify_tool_output, identify_tool_total = extract_token_metrics(context.identify_tool_collector)
    create_tool_input, create_tool_output, create_tool_total = extract_token_metrics(context.create_tool_collector)
    identify_faulty_input, identify_faulty_output, identify_faulty_total = extract_token_metrics(context.identify_faulty_collector)
    debug_tool_input, debug_tool_output, debug_tool_total = extract_token_metrics(context.debug_tool_collector)
    
    # NEW: Extract test and assessment metrics
    test_cobbie_input, test_cobbie_output, test_cobbie_total = extract_token_metrics(context.test_cobbie_collector)
    test_verify_input, test_verify_output, test_verify_total = extract_token_metrics(context.test_verify_collector)
    tool_assess_input, tool_assess_output, tool_assess_total = extract_token_metrics(context.tool_assessment_collector)
    
    # Calculate totals (including new components)
    total_tokens = (
        cobbie_total + verify_total + identify_tool_total + create_tool_total +
        identify_faulty_total + debug_tool_total +
        test_cobbie_total + test_verify_total + tool_assess_total
    )
    total_duration = (
        context.cobbie_duration + context.verify_duration +
        context.identify_tool_duration + context.create_tool_duration +
        context.identify_faulty_duration + context.debug_tool_duration +
        context.test_cobbie_duration + context.test_verify_duration +
        context.tool_assessment_duration
    )
    
    # Get classification
    classification = context.verify_result.classification if context.verify_result else "unknown"
    
    # Build metrics dictionary
    metrics = {
        # Original metrics
        "cobbie_duration": context.cobbie_duration,
        "cobbie_input_tokens": cobbie_input,
        "cobbie_output_tokens": cobbie_output,
        "cobbie_total_tokens": cobbie_total,
        "verify_duration": context.verify_duration,
        "verify_input_tokens": verify_input,
        "verify_output_tokens": verify_output,
        "verify_total_tokens": verify_total,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        "answer_correct": 1 if classification == "correct" else 0,
        "answer_wrong": 1 if classification == "wrong" else 0,
        "answer_abstained": 1 if classification == "abstained" else 0,
        "tool_created": 1 if context.tool_created else 0,
        "tool_updated": 1 if context.tool_updated else 0,
        "tool_saved": 1 if context.tool_saved else 0,  # NEW
        "error": 1 if context.error_message else 0,
    }
    
    # Add Path A metrics if applicable
    if context.identify_tool_result:
        metrics.update({
            "identify_tool_duration": context.identify_tool_duration,
            "identify_tool_input_tokens": identify_tool_input,
            "identify_tool_output_tokens": identify_tool_output,
            "identify_tool_total_tokens": identify_tool_total,
        })
    
    if context.create_tool_result:
        metrics.update({
            "create_tool_duration": context.create_tool_duration,
            "create_tool_input_tokens": create_tool_input,
            "create_tool_output_tokens": create_tool_output,
            "create_tool_total_tokens": create_tool_total,
        })
    
    # Add Path B metrics if applicable
    if context.identify_faulty_result:
        metrics.update({
            "identify_faulty_duration": context.identify_faulty_duration,
            "identify_faulty_input_tokens": identify_faulty_input,
            "identify_faulty_output_tokens": identify_faulty_output,
            "identify_faulty_total_tokens": identify_faulty_total,
        })
    
    if context.debug_tool_result:
        metrics.update({
            "debug_tool_duration": context.debug_tool_duration,
            "debug_tool_input_tokens": debug_tool_input,
            "debug_tool_output_tokens": debug_tool_output,
            "debug_tool_total_tokens": debug_tool_total,
        })
    
    # NEW: Add tool testing metrics
    if context.test_cobbie_result:
        metrics.update({
            "test_cobbie_duration": context.test_cobbie_duration,
            "test_cobbie_input_tokens": test_cobbie_input,
            "test_cobbie_output_tokens": test_cobbie_output,
            "test_cobbie_total_tokens": test_cobbie_total,
            "test_verify_duration": context.test_verify_duration,
            "test_verify_input_tokens": test_verify_input,
            "test_verify_output_tokens": test_verify_output,
            "test_verify_total_tokens": test_verify_total,
        })
    
    # NEW: Add tool assessment metrics
    if context.tool_assessment:
        metrics.update({
            "tool_assessment_duration": context.tool_assessment_duration,
            "tool_assessment_input_tokens": tool_assess_input,
            "tool_assessment_output_tokens": tool_assess_output,
            "tool_assessment_total_tokens": tool_assess_total,
            "tool_was_used": 1 if context.tool_assessment.tool_was_used else 0,
            "tool_usage_helpful": 1 if context.tool_assessment.tool_usage_quality == "helpful" else 0,
            "tool_usage_harmful": 1 if context.tool_assessment.tool_usage_quality == "harmful" else 0,
            "tool_recommendation_keep": 1 if context.tool_assessment.recommendation == "keep_tool" else 0,
            "tool_recommendation_discard": 1 if context.tool_assessment.recommendation == "discard_tool" else 0,
        })
    
    # Log to MLflow
    mlflow.log_metrics(metrics)
    
    # Return dictionary for aggregate calculation
    return {
        "question_id": context.qa_pair.id,
        "classification": classification,
        "tool_created": context.tool_created,
        "tool_updated": context.tool_updated,
        "tool_saved": context.tool_saved,  # NEW
        "error": bool(context.error_message),
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        # NEW: Tool assessment data
        "tool_was_tested": bool(context.tool_assessment),
        "tool_recommendation": context.tool_assessment.recommendation if context.tool_assessment else None,
        "tool_usage_quality": context.tool_assessment.tool_usage_quality if context.tool_assessment else None,
    }
```

**Update `calculate_aggregate_metrics()`:**

```python
def calculate_aggregate_metrics(qa_results: List[dict]) -> dict:
    """Calculate aggregate metrics across all QA pairs."""
    
    total_count = len(qa_results)
    correct_count = sum(1 for r in qa_results if r.get("classification") == "correct")
    wrong_count = sum(1 for r in qa_results if r.get("classification") == "wrong")
    abstained_count = sum(1 for r in qa_results if r.get("classification") == "abstained")

    tools_created = sum(1 for r in qa_results if r.get("tool_created"))
    tools_updated = sum(1 for r in qa_results if r.get("tool_updated"))
    tools_saved = sum(1 for r in qa_results if r.get("tool_saved"))  # NEW
    tools_tested = sum(1 for r in qa_results if r.get("tool_was_tested"))  # NEW
    tools_kept = sum(1 for r in qa_results if r.get("tool_recommendation") == "keep_tool")  # NEW
    tools_discarded = sum(1 for r in qa_results if r.get("tool_recommendation") == "discard_tool")  # NEW
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
        "tools_saved": tools_saved,  # NEW
        "tools_tested": tools_tested,  # NEW
        "tools_kept": tools_kept,  # NEW
        "tools_discarded": tools_discarded,  # NEW
        "errors": errors,
        "success_rate": correct_count / total_count if total_count > 0 else 0,
        "tool_creation_rate": tools_created / correct_count if correct_count > 0 else 0,
        "tool_update_rate": tools_updated / wrong_count if wrong_count > 0 else 0,
        "tool_save_rate": tools_saved / tools_tested if tools_tested > 0 else 0,  # NEW
        "tool_keep_rate": tools_kept / tools_tested if tools_tested > 0 else 0,  # NEW
        "avg_tokens_per_qa": total_tokens / total_count if total_count > 0 else 0,
        "avg_duration_per_qa": total_duration / total_count if total_count > 0 else 0,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
    }
```

---

## 4. Updated Training Workflow

### Complete State Machine Flow

```
START
  ↓
RUN_COBBIE (Run Cobbie to answer question)
  ↓
VERIFY_ANSWER (Verify if answer is correct)
  ↓
  ├─→ [correct] → IDENTIFY_NEW_TOOL
  │                    ↓
  │                    ├─→ [new_tool=True] → CREATE_NEW_TOOL
  │                    │                           ↓
  │                    │                      TEST_TOOL_WITH_COBBIE
  │                    │                           ↓
  │                    │                      ASSESS_TOOL_USAGE
  │                    │                           ↓
  │                    │                      DECIDE_TOOL_FATE → END
  │                    │
  │                    └─→ [new_tool=False] → END
  │
  ├─→ [wrong] → IDENTIFY_FAULTY_TOOL
  │                  ↓
  │                  ├─→ [faulty_tool=True] → DEBUG_FAULTY_TOOL
  │                  │                              ↓
  │                  │                         TEST_TOOL_WITH_COBBIE
  │                  │                              ↓
  │                  │                         ASSESS_TOOL_USAGE
  │                  │                              ↓
  │                  │                         DECIDE_TOOL_FATE → END
  │                  │
  │                  └─→ [faulty_tool=False] → END
  │
  └─→ [abstained] → END

ERROR (Continue to next QA pair)
END (Move to next QA pair)
```

### Tool Testing Phase Details

**TEST_TOOL_WITH_COBBIE:**
1. Create temporary function from tool implementation
2. Add tool to test environment
3. Enhance question: "NOTE: A helper function `{name}` was recently created. If relevant, consider using it."
4. Run Cobbie with enhanced question and test tools
5. Capture execution history and results

**ASSESS_TOOL_USAGE:**
1. Verify test answer correctness
2. Call `assess_helper_function` agent
3. Analyze execution history for tool usage patterns
4. Return assessment with recommendation

**DECIDE_TOOL_FATE:**
1. Examine assessment recommendation
2. Apply decision logic:
   - `keep_tool` → Save permanently, reload tools
   - `discard_tool` → Don't save, log reason
   - `improve_tool` → Don't save, flag for review
   - `unclear` → Save tentatively, tag for review
3. Update context and metrics

---

## 5. Testing Strategy

### Unit Testing

Test each component independently:

1. **Schema Validation (`baml_src/schemas.baml`):**
   - Verify `HelperFunctionAssessment` class compiles
   - Test all enum values are valid

2. **BAML Function (`baml_src/assess_helper_function.baml`):**
   - Run provided test cases (Helpful, NotUsed, Misused, Harmful)
   - Verify function returns correct schema type
   - Check test cases cover all `tool_usage_quality` values

3. **Python Agent (`src/agents/assess_helper_function.py`):**
   - Test with mock execution histories
   - Verify MLflow integration works
   - Check token metrics extraction
   - Test error handling

4. **State Handlers (`scripts/run_training_phase.py`):**
   - Test each new state handler with mock contexts
   - Verify state transitions are correct
   - Check metrics logging is complete

### Integration Testing

Test the full flow:

1. **Path A (Correct Answer) with Tool Testing:**
   ```
   START → RUN_COBBIE (correct) → IDENTIFY_NEW_TOOL (yes) 
     → CREATE_NEW_TOOL (success) → TEST_TOOL_WITH_COBBIE 
     → ASSESS_TOOL_USAGE → DECIDE_TOOL_FATE (keep) → END
   ```

2. **Path B (Wrong Answer) with Tool Testing:**
   ```
   START → RUN_COBBIE (wrong) → IDENTIFY_FAULTY_TOOL (yes) 
     → DEBUG_FAULTY_TOOL (success) → TEST_TOOL_WITH_COBBIE 
     → ASSESS_TOOL_USAGE → DECIDE_TOOL_FATE (keep) → END
   ```

3. **Tool Discarding Scenario:**
   ```
   CREATE_NEW_TOOL → TEST_TOOL_WITH_COBBIE 
     → ASSESS_TOOL_USAGE (harmful) → DECIDE_TOOL_FATE (discard) → END
   ```

### End-to-End Testing

Run on real dataset:

1. **Small Dataset (5-10 QA pairs):**
   - Verify state machine completes without crashes
   - Check MLflow hierarchy is correct
   - Validate tool creation and testing flow
   - Confirm metrics are logged properly

2. **Medium Dataset (20-50 QA pairs):**
   - Monitor tool save/discard rates
   - Analyze assessment patterns
   - Check for memory leaks
   - Measure performance impact

3. **Full Dataset:**
   - Compare results with/without testing enabled
   - Analyze tool quality improvements
   - Calculate ROI (cost vs. benefit)

---

## 6. Success Criteria

The implementation is successful when:

✅ **Functional Requirements:**
- All QA pairs are processed without crashing
- Tools are tested before being saved permanently
- Assessment provides clear recommendations (keep/discard/improve)
- Tool fate decisions are executed correctly
- MLflow logging captures all testing metrics

✅ **Quality Requirements:**
- Tool save rate improves (fewer broken tools saved)
- Assessment confidence is high (>70% high/medium)
- False positive rate is low (<10% harmful tools saved)
- False negative rate is low (<10% helpful tools discarded)

✅ **Performance Requirements:**
- Testing adds <2 minutes per tool on average
- Token cost increase is <50% per QA pair with tool
- Memory usage remains stable throughout run

✅ **Integration Requirements:**
- No breaking changes to existing agents
- State machine remains maintainable
- MLflow hierarchy matches evaluation pattern
- Metrics aggregate correctly

---

## 7. Cost-Benefit Analysis

### Estimated Costs (per tool tested)

| Component | Tokens | Cost (GLM-4.6) | Time |
|-----------|--------|----------------|------|
| TEST_TOOL_WITH_COBBIE | 5,000-15,000 | $0.05-0.15 | 30-120s |
| ASSESS_TOOL_USAGE (verify) | 500-1,000 | $0.005-0.01 | 2-5s |
| ASSESS_TOOL_USAGE (assess) | 1,500-3,000 | $0.015-0.03 | 3-8s |
| **Total per tool** | **7,000-19,000** | **$0.07-0.19** | **35-133s** |

### Estimated Benefits

**Scenario 1: Prevents saving 1 broken tool**
- Broken tool could cause 10+ wrong answers before detected
- Each wrong answer wastes: debugging effort + potential wrong tool creation
- **Benefit:** Saves ~10× the testing cost

**Scenario 2: Confirms 1 helpful tool**
- Helpful tool used in 5+ future questions
- Each usage saves: Cobbie iterations + faster answers
- **Benefit:** 5× ROI minimum

**Scenario 3: Identifies tool for improvement**
- Instead of saving broken tool, flags for retry
- Prevents negative impact on future questions
- **Benefit:** Maintains system quality

### Break-Even Analysis

If testing **prevents 1 harmful tool** or **confirms 2 helpful tools** per 10 tests, the feature pays for itself.

---

## 8. Future Enhancements

### Phase 2: Multi-Test Validation

Instead of testing with one QA pair, test with multiple:

```python
def handle_test_tool_with_multiple_questions(context: Context):
    """Test tool with 3-5 similar QA pairs from the dataset."""
    # Retrieve similar questions from database
    similar_qa_pairs = get_similar_questions(context.qa_pair, limit=3)
    
    # Test tool with each question
    test_results = []
    for qa in similar_qa_pairs:
        # Run Cobbie with enhanced question
        result = test_with_question(qa, context.tool_name)
        test_results.append(result)
    
    # Aggregate assessment across all tests
    return aggregate_assessments(test_results)
```

**Benefits:**
- More robust validation
- Detects overfitting to single question
- Higher confidence in assessments

**Costs:**
- 3-5× testing cost
- Longer execution time

### Phase 3: Gradual Rollout

Instead of binary keep/discard, implement confidence-based rollout:

```python
class ToolConfidenceLevel(Enum):
    HIGH = "high"      # Always use (80%+ success rate)
    MEDIUM = "medium"  # Use with 50% probability
    LOW = "low"        # Use with 20% probability (A/B testing)
    TESTING = "testing" # Use only in test mode
```

**Benefits:**
- Safer deployment of uncertain tools
- Continuous learning from usage
- A/B testing capability

### Phase 4: Automated Improvement Loop

If tool needs improvement, automatically retry:

```python
if assessment.recommendation == "improve_tool":
    # Use assessment feedback to improve
    improved_tool = debug_helper_function(
        tool_implementation=original_implementation,
        error_description=assessment.usage_details,
        # ... other params
    )
    
    # Re-test improved version
    return TrainingState.TEST_TOOL_WITH_COBBIE, context
```

**Benefits:**
- Self-healing tool creation
- Higher success rate
- Fewer manual interventions

---

## 9. Migration Plan

### Step 1: Implement Core Components (Week 1)

1. Add `HelperFunctionAssessment` schema
2. Implement `HelperFunctionAssessor` BAML function
3. Create `assess_helper_function.py` agent
4. Write unit tests

### Step 2: Update State Machine (Week 1-2)

1. Add new states to enum
2. Update `Context` class
3. Modify existing state handlers
4. Implement new state handlers
5. Update `process_state()` dispatcher

### Step 3: Testing & Validation (Week 2)

1. Run unit tests
2. Run integration tests with small dataset
3. Fix bugs and edge cases
4. Optimize performance

### Step 4: Production Deployment (Week 3)

1. Run full training on complete dataset
2. Compare metrics with baseline (no testing)
3. Analyze tool quality improvements
4. Document findings

### Step 5: Monitoring & Iteration (Ongoing)

1. Monitor tool save/discard rates
2. Collect feedback on assessment quality
3. Refine recommendation logic
4. Implement Phase 2 enhancements if needed

---

## 10. Implementation Checklist

### BAML Components

- [ ] Add `HelperFunctionAssessment` class to `baml_src/schemas.baml`
- [ ] Create `baml_src/assess_helper_function.baml` with:
  - [ ] `HelperFunctionAssessor` function
  - [ ] 4 test cases (Helpful, NotUsed, Misused, Harmful)
- [ ] Run `baml-cli generate` to update Python types

### Python Agent

- [ ] Create `src/agents/assess_helper_function.py` with:
  - [ ] `assess_helper_function()` main function
  - [ ] MLflow integration
  - [ ] Token metrics extraction
  - [ ] Error handling
- [ ] Add export to `src/agents/__init__.py`
- [ ] Write unit tests

### State Machine Updates

- [ ] Update `TrainingState` enum with:
  - [ ] `TEST_TOOL_WITH_COBBIE`
  - [ ] `ASSESS_TOOL_USAGE`
  - [ ] `DECIDE_TOOL_FATE`
- [ ] Update `Context` class with:
  - [ ] Test Cobbie results fields
  - [ ] Tool assessment fields
  - [ ] `tool_saved` boolean
- [ ] Modify existing handlers:
  - [ ] `handle_create_new_tool()` - don't save immediately
  - [ ] `handle_debug_faulty_tool()` - don't save immediately
- [ ] Implement new handlers:
  - [ ] `handle_test_tool_with_cobbie()`
  - [ ] `handle_assess_tool_usage()`
  - [ ] `handle_decide_tool_fate()`
- [ ] Update `process_state()` dispatcher

### Metrics & Logging

- [ ] Update `log_qa_metrics()` with:
  - [ ] Test Cobbie metrics
  - [ ] Assessment metrics
  - [ ] Tool fate metrics
- [ ] Update `calculate_aggregate_metrics()` with:
  - [ ] `tools_saved`
  - [ ] `tools_tested`
  - [ ] `tools_kept`
  - [ ] `tools_discarded`
  - [ ] `tool_save_rate`
  - [ ] `tool_keep_rate`

### Testing

- [ ] Unit tests for BAML function
- [ ] Unit tests for Python agent
- [ ] Unit tests for state handlers
- [ ] Integration tests (Paths A & B)
- [ ] Small dataset test (5-10 QA pairs)
- [ ] Medium dataset test (20-50 QA pairs)
- [ ] Performance profiling

### Documentation

- [ ] Update training phase specification
- [ ] Add agent implementation guidelines
- [ ] Document decision logic
- [ ] Create troubleshooting guide

---

## 11. Risk Assessment

### High-Risk Areas

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Testing adds too much cost/time | Medium | High | Monitor metrics, add early stopping if test fails quickly |
| Assessment provides unclear recommendations | Medium | Medium | Improve prompt with examples, add confidence thresholds |
| Tool testing breaks existing flow | Low | High | Comprehensive integration testing, feature flag for gradual rollout |
| False negatives (discard good tools) | Medium | Medium | Conservative decision logic (unclear → keep), log all discards for review |

### Medium-Risk Areas

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Enhanced question biases Cobbie | Low | Medium | Keep enhancement subtle, analyze usage patterns |
| Token metrics extraction fails | Low | Low | Graceful fallback to zero, log warnings |
| MLflow logging errors | Low | Medium | Try-except blocks, continue on logging failure |

---

## 12. Rollback Plan

If the feature causes issues:

1. **Quick Rollback (1 hour):**
   - Set feature flag to skip testing states
   - Fall back to immediate save behavior
   - Keep all metrics logging intact

2. **Partial Rollback (1 day):**
   - Disable assessment, keep basic re-run
   - Use simple heuristic (answer correct → keep)
   - Maintain MLflow integration

3. **Full Rollback (1 week):**
   - Revert all state machine changes
   - Remove new agents
   - Restore original training flow

---

## 13. References

- **Training Phase Spec:** `specs/training_phase.md`
- **Evaluation Pattern:** `scripts/run_evaluation.py`
- **Similar Agents:**
  - `src/agents/identify_helper_function.py`
  - `src/agents/faulty_tool_identifier.py`
- **Test & Improve Pattern:** `src/engine/components/test_and_improve_baml.py` (inspiration, not directly used)
- **BAML Schemas:** `baml_src/schemas.baml`
- **Agent Guidelines:** `src/agents/agents_implementation_guideline.md`

---

## Appendix A: Example Enhanced Question

**Original Question:**
```
How many doors are on the ground floor?
```

**Enhanced Question:**
```
How many doors are on the ground floor?

NOTE: A helper function `get_elements_by_building_storey` was recently created. 
If it seems relevant, consider using it to help answer this question.
```

**Rationale:**
- Gentle suggestion, not a command
- Preserves original question intent
- Cobbie can still choose alternative approach
- Clear context for assessment agent

---

## Appendix B: Decision Logic Flowchart

```
┌─────────────────────────┐
│  Tool Assessment Result │
└───────────┬─────────────┘
            │
            ├─→ recommendation: "keep_tool"
            │   ├─→ Save tool permanently
            │   ├─→ Reload tools
            │   └─→ Log: "✅ Tool saved"
            │
            ├─→ recommendation: "discard_tool"
            │   ├─→ Don't save
            │   └─→ Log: "❌ Tool discarded"
            │
            ├─→ recommendation: "improve_tool"
            │   ├─→ Don't save
            │   ├─→ Flag for review
            │   └─→ Log: "⚠️ Needs improvement"
            │
            └─→ recommendation: "unclear"
                ├─→ Save tentatively (conservative)
                ├─→ Tag for manual review
                └─→ Log: "❓ Unclear, saved tentatively"
```

---

**End of Specification**
