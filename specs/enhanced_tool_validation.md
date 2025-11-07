# Enhanced Tool Validation Implementation Plan

## Overview

This document outlines the implementation plan for an enhanced tool validation approach in Cobbie's training phase. Instead of creating a dedicated testing agent that independently tests tools, we will use a **hybrid approach** that combines guided Cobbie execution with lightweight tool-specific assessment.

### Core Approach

1. **Guided Cobbie Testing**: Re-run Cobbie with an enhanced question that suggests using the new tool
2. **Tool-Specific Assessment**: Analyze the execution history to assess how the tool was used and its effectiveness
3. **Informed Decision Making**: Make keep/discard decisions based on the tool's actual contribution to answering the question

---

## Architecture Overview

### Workflow Integration

```
Path A (Correct Answer):
START → RUN_COBBIE → VERIFY_ANSWER (correct) → IDENTIFY_NEW_TOOL
  → CREATE_NEW_TOOL → TEST_TOOL_WITH_COBBIE → ASSESS_TOOL_USAGE → DECIDE_TOOL_FATE → END

Path B (Wrong Answer):
START → RUN_COBBIE → VERIFY_ANSWER (wrong) → IDENTIFY_FAULTY_TOOL
  → DEBUG_FAULTY_TOOL → TEST_TOOL_WITH_COBBIE → ASSESS_TOOL_USAGE → DECIDE_TOOL_FATE → END
```

### Key Components

1. **Enhanced Question**: Cobbie is guided to try using the new tool
2. **AssessHelperFunction**: BAML function that analyzes tool usage patterns
3. **ToolUsageAnalysis**: Schema for structured assessment results
4. **Tool Assessment Agent**: Python wrapper for the BAML function
5. **Updated State Machine**: New validation states in training workflow

---

## Implementation Details

## 1. Schema Design: `ToolUsageAnalysis`

### File: `baml_src/schemas.baml`

```baml
// Tool usage assessment result from AssessHelperFunction - analyzes how a specific tool contributed to answering a question
class ToolUsageAnalysis {
  thoughts string @description("Step-by-step analysis of the execution history to understand tool usage patterns")

  tool_was_used bool @description("Whether the target tool was actually called during execution")

  tool_usage_quality "helpful" | "not_used" | "ignored" | "misused" | "harmful" @description(#"
    Assessment of how the tool contributed to the question-answering process:
    - helpful: Tool was used correctly and directly contributed to the answer
    - not_used: Tool was available but Cobbie chose not to use it
    - ignored: Tool was considered but deemed irrelevant for this question
    - misused: Tool was used with incorrect parameters or in wrong context
    - harmful: Tool was used and led to incorrect results or confusion
  "#)

  usage_details string @description("Detailed explanation of tool usage patterns, how it was called, what it returned, and how that contributed to the final answer")

  recommendation "keep_tool" | "discard_tool" | "improve_tool" | "unclear" @description(#"
    Final recommendation based on the tool's performance:
    - keep_tool: Tool was helpful and should be saved
    - discard_tool: Tool was not useful or was detrimental
    - improve_tool: Tool has potential but needs refinement
    - unclear: Insufficient evidence to make definitive decision
  "#)

  confidence "high" | "medium" | "low" @description(#"
    Confidence level in this assessment:
    - high: Clear evidence from execution history
    - medium: Good evidence but some ambiguity
    - low: Limited evidence or conflicting indicators
  "#)

  execution_examples string? @description("Specific code snippets from execution history showing tool usage (or lack thereof)")
}
```

### Naming Pattern Justification

Following the existing naming conventions observed in the codebase:
- **Analysis**: `NewToolAnalysis`, `FaultyToolAnalysis` → `ToolUsageAnalysis`
- **Result**: `SimilarityResult`, `AnswerEvaluationResult` → Used `Analysis` for consistency with tool-related schemas
- **Pattern**: Uses descriptive fields with clear documentation, similar to `FaultyToolAnalysis`

---

## 2. BAML Function: `AssessHelperFunction`

### File: `baml_src/assess_helper_function.baml`

```baml
// AssessHelperFunction - Analyzes execution history to evaluate how a specific tool was used
// This agent examines Cobbie's execution with a newly created or updated tool to determine its usefulness
// Provides targeted feedback on tool utility rather than general assessment

function AssessHelperFunction(
  execution_history: string @description("Complete execution history from Cobbie during guided testing: thoughts, code, results, and final answer"),
  original_question: string @description("The original question that was answered during the initial Cobbie run"),
  ground_truth_answer: string @description("The correct/expected answer to the original question"),
  tested_tool_name: string @description("Name of the helper function that was being tested"),
  tested_tool_description: string @description("Description of what the tested tool is supposed to do"),
  final_answer: string @description("The answer provided by Cobbie during the guided test run"),
  answer_correctness: "correct" | "wrong" | "abstained" @description("Whether the guided test answer was classified as correct, wrong, or abstained"),
  question_was_enhanced: bool @description("Whether the question included guidance about using the specific tool")
) -> ToolUsageAnalysis {
  client GLM_4_6
  prompt #"
    You are an expert software architect and testing specialist for BIM (Building Information Modeling) systems.

    Your task is to analyze whether a specific helper function was useful during a guided question-answering session with Cobbie.

    TESTING CONTEXT:

    Original Question:
    {{ original_question }}

    Ground Truth Answer:
    {{ ground_truth_answer }}

    Tool Being Tested:
    Name: {{ tested_tool_name }}
    Description: {{ tested_tool_description }}

    Question Enhancement: {{ question_was_enhanced ? "Yes - Cobbie was guided to try using this tool" : "No - Standard question" }}

    Final Answer from Guided Test:
    {{ final_answer }}

    Answer Correctness: {{ answer_correctness }}

    Complete Execution History:
    {{ execution_history }}

    YOUR ANALYSIS TASK:

    Evaluate how the tested tool contributed to Cobbie's question-answering process. Focus specifically on:
    1. Whether the tool was actually used
    2. If used, whether it was used correctly
    3. Whether the tool helped achieve the correct answer
    4. The overall utility and quality of the tool

    ANALYSIS FRAMEWORK:

    **Tool Usage Detection:**
    - Search for calls to `{{ tested_tool_name }}` in the execution history
    - Note the parameters used and the returned values
    - Check how the tool's output was used in subsequent reasoning

    **Usage Quality Assessment:**
    - **helpful**: Tool was used correctly and its output directly contributed to the answer
    - **not_used**: Tool was available but Cobbie chose alternative approaches
    - **ignored**: Tool was considered but dismissed as irrelevant
    - **misused**: Tool called with wrong parameters or in inappropriate context
    - **harmful**: Tool usage led to incorrect results or confused the reasoning

    **Contributivity Analysis:**
    - Compare the guided test answer with the original Cobbie answer (from context)
    - Did the tool help achieve better accuracy?
    - Did the tool enable a more efficient solution?
    - Was the tool essential or just convenient?

    CRITICAL EVALUATION CRITERIA:

    **Tool is HELPFUL if:**
    - Correctly used and contributed to correct answer
    - Provided essential functionality not easily achieved otherwise
    - Enabled more efficient or elegant solution
    - Would be valuable for similar future questions

    **Tool should be DISCARDED if:**
    - Not used when it could have been helpful
    - Used incorrectly or caused errors
    - Provided no meaningful contribution
    - Replaced by simpler approaches

    **Tool needs IMPROVEMENT if:**
    - Used but with difficulty or errors
    - Potential utility but poor implementation
    - Wrong interface or return format
    - Could be more efficient or robust

    **UNCLEAR assessment when:**
    - Limited usage or insufficient test coverage
    - Mixed indicators of utility
    - Edge case or question-specific scenario

    DETAILED REQUIREMENTS:

    1. **Trace Tool Usage**: Identify every call to `{{ tested_tool_name }}` with context
    2. **Validate Usage**: Check if parameters were correct and results reasonable
    3. **Assess Contribution**: Evaluate how the tool's output influenced the final answer
    4. **Consider Alternatives**: Compare with how Cobbie solved it without the tool
    5. **Project Future Value**: Consider utility for other similar questions

    EXECUTION EXAMPLES TO INCLUDE:
    - If tool was used: Show the actual code calls and results
    - If tool was ignored: Explain why Cobbie might have avoided it
    - If tool failed: Document the errors or incorrect behavior

    {{ ctx.output_format }}
  "#
}

// Test case 1: Tool was helpful - correctly used and contributed to answer
test AssessHelperFunctionHelpfulTest {
  functions [AssessHelperFunction]
  args {
    original_question "How many doors have a fire rating of at least 30 minutes?"
    ground_truth_answer "There are 3 doors with a fire rating of at least 30 minutes."
    tested_tool_name "count_doors_by_fire_rating"
    tested_tool_description "Count doors that meet minimum fire rating requirements"
    final_answer "There are 3 doors with a fire rating of at least 30 minutes."
    answer_correctness "correct"
    question_was_enhanced true
    execution_history #"
      --- Iteration 1 ---
      Thoughts: The question mentions I should try using the count_doors_by_fire_rating function for this question about fire ratings.

      Code:
      result = count_doors_by_fire_rating(path_ifc_model, min_fire_rating=30)
      print(f"Doors with fire rating >= 30 minutes: {result}")

      Result:
      Doors with fire rating >= 30 minutes: 3

      --- Final Answer ---
      Thoughts: The count_doors_by_fire_rating function correctly returned 3 doors with fire rating >= 30 minutes, which matches the expected result.
      Answer: There are 3 doors with a fire rating of at least 30 minutes.
    "#
  }
}

// Test case 2: Tool was not used - Cobbie found alternative solution
test AssessHelperFunctionNotUsedTest {
  functions [AssessHelperFunction]
  args {
    original_question "What is the total area of all walls in the building?"
    ground_truth_answer "The total area of all walls is 850 square meters."
    tested_tool_name "calculate_wall_areas"
    tested_tool_description "Calculate total area of all walls in a BIM model"
    final_answer "The total area of all walls is 850 square meters."
    answer_correctness "correct"
    question_was_enhanced true
    execution_history #"
      --- Iteration 1 ---
      Thoughts: I need to calculate wall areas. The question mentions trying the calculate_wall_areas function, but let me first check if I can do this more directly.

      Code:
      import ifcopenshell
      model = ifcopenshell.open(path_ifc_model)
      walls = model.by_type('IfcWall')

      total_area = 0
      for wall in walls:
          if hasattr(wall, 'QuantitySets'):
              for qset in wall.QuantitySets:
                  if qset.Name == 'BaseQuantities':
                      for qto in qset.Quantities:
                          if qto.Name == 'NetArea':
                              total_area += qto.AreaValue

      print(f"Total wall area: {total_area}")

      Result:
      Total wall area: 850.0

      --- Final Answer ---
      Thoughts: I was able to calculate wall areas directly from IFC quantities without needing the specialized function.
      Answer: The total area of all walls is 850 square meters.
    "#
  }
}

// Test case 3: Tool was misused - called with wrong parameters
test AssessHelperFunctionMisusedTest {
  functions [AssessHelperFunction]
  args {
    original_question "Find all load-bearing columns in the structure."
    ground_truth_answer "There are 12 load-bearing columns in the building."
    tested_tool_name "filter_elements_by_property"
    tested_tool_description "Filter IFC elements by property value"
    final_answer "I encountered an error when trying to use the filter_elements_by_property function."
    answer_correctness "wrong"
    question_was_enhanced true
    execution_history #"
      --- Iteration 1 ---
      Thoughts: The question suggests using the filter_elements_by_property function to find load-bearing columns.

      Code:
      columns = filter_elements_by_property(path_ifc_model, 'IfcColumn', 'IsLoadBearing', True)
      print(f"Load-bearing columns found: {len(columns)}")

      Result:
      Error: Property 'IsLoadBearing' not found in element property sets

      --- Iteration 2 ---
      Thoughts: The function failed because I used the wrong property name. Let me try a different property.

      Code:
      columns = filter_elements_by_property(path_ifc_model, 'IfcColumn', 'LoadBearing', True)
      print(f"Load-bearing columns found: {len(columns)}")

      Result:
      Error: Property 'LoadBearing' not found in element property sets

      --- Final Answer ---
      Thoughts: The filter_elements_by_property function keeps failing because I'm using incorrect property names. I need to understand the correct property structure first.
      Answer: I encountered an error when trying to use the filter_elements_by_property function.
    "#
  }
}
```

---

## 3. Python Agent Implementation

### File: `src/agents/assess_helper_function.py`

```python
"""
Agent that assesses helper function usage during guided testing.
Analyzes Cobbie execution history to determine if a specific tool was useful.
"""

import time
from typing import Tuple

import mlflow
from baml_py.baml_py import Collector
from baml_client import b
from baml_client.types import ToolUsageAnalysis
from src.config import LOG_LEVEL
from src.util import get_logger

# Initialize logger
_logger = get_logger(name="baml_assess_helper_function", log_level=LOG_LEVEL)


def assess_helper_function(
    execution_history: str,
    original_question: str,
    ground_truth_answer: str,
    tested_tool_name: str,
    tested_tool_description: str,
    final_answer: str,
    answer_correctness: str,
    question_was_enhanced: bool = True,
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[ToolUsageAnalysis, Collector]:
    """
    Assess whether a specific helper function was useful during Cobbie's guided testing.

    Args:
        execution_history: Complete execution history from Cobbie during guided testing
        original_question: The original question that was answered initially
        ground_truth_answer: The correct/expected answer to the original question
        tested_tool_name: Name of the helper function that was being tested
        tested_tool_description: Description of what the tested tool is supposed to do
        final_answer: The answer provided by Cobbie during the guided test run
        answer_correctness: Whether the guided test answer was correct, wrong, or abstained
        question_was_enhanced: Whether the question included guidance about using the specific tool
        llm_provider: LLM provider name for logging (default: "zai")
        llm_name: LLM model name for logging (default: "GLM-4.6")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (ToolUsageAnalysis, Collector) where ToolUsageAnalysis contains:
        - thoughts: Analysis of tool usage patterns
        - tool_was_used: Whether the target tool was actually called
        - tool_usage_quality: Assessment of how the tool contributed
        - usage_details: Detailed explanation of tool usage
        - recommendation: Final recommendation (keep/discard/improve)
        - confidence: Confidence level in the assessment
        - execution_examples: Specific code examples from execution history
    """
    # Start timer
    start = time.time()

    # Create collector for token tracking
    collector = Collector(name="AssessHelperFunction")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    with mlflow.start_span(
        name="AssessHelperFunction", span_type="LLM"
    ) as assessment_span:
        assessment_span.set_inputs(
            {
                "execution_history": execution_history[:500] + "..." if len(execution_history) > 500 else execution_history,
                "original_question": original_question,
                "ground_truth_answer": ground_truth_answer,
                "tested_tool_name": tested_tool_name,
                "tested_tool_description": tested_tool_description,
                "final_answer": final_answer,
                "answer_correctness": answer_correctness,
                "question_was_enhanced": question_was_enhanced,
            }
        )

        # Assess helper function usage
        try:
            assessment_result = b.with_options(
                **kwargs.pop("baml_options", {})
            ).AssessHelperFunction(
                execution_history=execution_history,
                original_question=original_question,
                ground_truth_answer=ground_truth_answer,
                tested_tool_name=tested_tool_name,
                tested_tool_description=tested_tool_description,
                final_answer=final_answer,
                answer_correctness=answer_correctness,
                question_was_enhanced=question_was_enhanced,
                **kwargs,
            )
        except Exception as e:
            _logger.error(f"Error assessing helper function: {e}")
            assessment_result = ToolUsageAnalysis(
                thoughts=f"An Exception occurred when trying to assess helper function usage. Exception:\n{e}",
                tool_was_used=False,
                tool_usage_quality="not_used",
                usage_details="Assessment failed due to an error",
                recommendation="unclear",
                confidence="low",
                execution_examples=None,
            )

        # Log outputs
        assessment_span.set_outputs(
            {
                "tool_was_used": assessment_result.tool_was_used,
                "tool_usage_quality": assessment_result.tool_usage_quality,
                "recommendation": assessment_result.recommendation,
                "confidence": assessment_result.confidence,
                "thoughts": assessment_result.thoughts,
            }
        )

        # Calculate metrics
        duration = time.time() - start
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0

        # Extract token usage from collector
        if collector and hasattr(collector, "usage") and collector.usage:
            usage = collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens

        # Log metrics to MLflow
        mlflow.log_metrics(
            {
                "assess_helper_function_input_tokens": input_tokens,
                "assess_helper_function_output_tokens": output_tokens,
                "assess_helper_function_total_tokens": total_tokens,
                "assess_helper_function_duration": duration,
                "assess_helper_function_tool_used": 1 if assessment_result.tool_was_used else 0,
                "assess_helper_function_helpful": 1 if assessment_result.tool_usage_quality == "helpful" else 0,
                "assess_helper_function_keep_recommendation": 1 if assessment_result.recommendation == "keep_tool" else 0,
                "assess_helper_function_confidence_high": 1 if assessment_result.confidence == "high" else 0,
            }
        )

        _logger.info(
            f"Helper function assessment completed. "
            f"Tool: {tested_tool_name}, "
            f"Used: {assessment_result.tool_was_used}, "
            f"Quality: {assessment_result.tool_usage_quality}, "
            f"Recommendation: {assessment_result.recommendation}, "
            f"Confidence: {assessment_result.confidence}, "
            f"Duration: {duration:.2f}s, "
            f"Tokens: {total_tokens}"
        )

        return assessment_result, collector


if __name__ == "__main__":
    import mlflow
    from src.config import TEST_IFC_PATH

    # Setup MLflow for testing
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("AssessHelperFunction")

    # Example test data
    test_execution_history = """
    --- Iteration 1 ---
    Thoughts: I should try using the count_doors_by_fire_rating function for this fire rating question.

    Code:
    result = count_doors_by_fire_rating(path_ifc_model, min_fire_rating=30)
    print(f"Doors with fire rating >= 30 minutes: {result}")

    Result:
    Doors with fire rating >= 30 minutes: 3

    --- Final Answer ---
    Thoughts: The function worked correctly and returned the expected result.
    Answer: There are 3 doors with a fire rating of at least 30 minutes.
    """

    # Run assessment
    assessment, collector = assess_helper_function(
        execution_history=test_execution_history,
        original_question="How many doors have a fire rating of at least 30 minutes?",
        ground_truth_answer="There are 3 doors with a fire rating of at least 30 minutes.",
        tested_tool_name="count_doors_by_fire_rating",
        tested_tool_description="Count doors that meet minimum fire rating requirements",
        final_answer="There are 3 doors with a fire rating of at least 30 minutes.",
        answer_correctness="correct",
        question_was_enhanced=True,
        llm_provider="zai",
        llm_name="GLM-4.6",
    )

    print("=" * 80)
    print("ASSESSMENT RESULTS")
    print("=" * 80)
    print(f"Tool was used: {assessment.tool_was_used}")
    print(f"Usage quality: {assessment.tool_usage_quality}")
    print(f"Recommendation: {assessment.recommendation}")
    print(f"Confidence: {assessment.confidence}")
    print(f"\nThoughts:\n{assessment.thoughts}")
    print(f"\nUsage Details:\n{assessment.usage_details}")
    if assessment.execution_examples:
        print(f"\nExecution Examples:\n{assessment.execution_examples}")
```

---

## 4. State Machine Updates

### File: `scripts/run_training_phase.py`

#### 4.1 Updated Enum

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

    # New validation states (applies to both paths)
    TEST_TOOL_WITH_COBBIE = auto()
    ASSESS_TOOL_USAGE = auto()
    DECIDE_TOOL_FATE = auto()

    # Terminal states
    END = auto()
    ERROR = auto()
```

#### 4.2 Updated Context Class

```python
from baml_client.types import ToolUsageAnalysis

class Context(BaseModel):
    # ... existing fields ...

    # Tool testing results (new)
    test_cobbie_result: Optional[FinalAnswer] = None
    test_cobbie_collector: Optional[Collector] = None
    test_cobbie_history: str = ""
    test_cobbie_duration: float = 0.0
    test_answer_correctness: Optional[str] = None  # "correct" | "wrong" | "abstained"

    # Tool assessment results (new)
    tool_assessment: Optional[ToolUsageAnalysis] = None
    tool_assessment_collector: Optional[Collector] = None
    tool_assessment_duration: float = 0.0

    # Final decision (new)
    tool_saved: bool = False  # Final decision: keep or discard
    question_was_enhanced: bool = True  # Track if we used enhanced question
```

#### 4.3 New State Handlers

```python
def handle_test_tool_with_cobbie(context: Context) -> Tuple[TrainingState, Context]:
    """
    Re-run Cobbie with enhanced question to test new or updated tool.

    This state validates whether the newly created or debugged tool is actually useful
    by having Cobbie attempt to answer the same question with guidance to use the tool.
    """
    import time
    from src.agents import cobbie

    # Enhance the question to guide Cobbie toward using the new tool
    enhanced_question = (
        f"{context.qa_pair.question}\n\n"
        f"NOTE: A new helper function `{context.tool_name}` was recently created. "
        f"If it seems relevant, consider using it to help answer this question."
    )

    with mlflow.start_span(name="TestToolWithCobbie", span_type="CHAIN") as span:
        start_time = time.time()

        try:
            # Get IFC model path
            ifc_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

            # Run Cobbie with enhanced question
            result, collector, history = cobbie(
                user_input=enhanced_question,
                tools=context.tools,  # Includes the new tool
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
                "enhanced_question": enhanced_question,
                "answer": result.answer,
                "thoughts": result.thoughts,
                "duration": context.test_cobbie_duration,
                "tool_name": context.tool_name,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            _logger.info(f"Tool test with Cobbie completed. Answer: {result.answer[:100]}...")

            return TrainingState.ASSESS_TOOL_USAGE, context

        except Exception as e:
            _logger.error(f"Error testing tool with Cobbie: {e}")
            context.error_message = f"Tool testing error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context


def handle_assess_tool_usage(context: Context) -> Tuple[TrainingState, Context]:
    """
    Analyze whether the tested tool was helpful during Cobbie's guided execution.

    This state assesses the tool's actual contribution to answering the question,
    providing targeted feedback on its utility and effectiveness.
    """
    import time
    from src.agents import verify_answer
    from src.agents.assess_helper_function import assess_helper_function

    with mlflow.start_span(name="AssessToolUsage", span_type="LLM") as span:
        start_time = time.time()

        try:
            # First, verify the test answer to know if it was correct
            verify_result, verify_collector = verify_answer(
                question=context.qa_pair.question,
                category=context.qa_pair.category,
                ground_truth=context.qa_pair.answer,
                system_response=context.test_cobbie_result.answer,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.test_answer_correctness = verify_result.classification

            # Get tool description based on the path taken
            if context.path_taken == "correct":  # Path A: new tool
                tool_description = (
                    context.identify_tool_result.new_tool_description
                    if context.identify_tool_result
                    else "New helper function"
                )
            else:  # Path B: debugged tool
                tool_description = (
                    context.identify_faulty_result.error_description
                    if context.identify_faulty_result
                    else "Debugged helper function"
                )

            # Assess tool usage
            assessment, collector = assess_helper_function(
                execution_history=context.test_cobbie_history,
                original_question=context.qa_pair.question,
                ground_truth_answer=context.qa_pair.answer,
                tested_tool_name=context.tool_name,
                tested_tool_description=tool_description,
                final_answer=context.test_cobbie_result.answer,
                answer_correctness=context.test_answer_correctness,
                question_was_enhanced=context.question_was_enhanced,
                llm_provider="zai",
                llm_name="GLM-4.6",
            )

            context.tool_assessment = assessment
            context.tool_assessment_collector = collector
            context.tool_assessment_duration = time.time() - start_time

            # Log to span
            span.set_outputs({
                "tool_was_used": assessment.tool_was_used,
                "tool_usage_quality": assessment.tool_usage_quality,
                "recommendation": assessment.recommendation,
                "confidence": assessment.confidence,
                "test_answer_correctness": context.test_answer_correctness,
                "duration": context.tool_assessment_duration,
            })

            # Extract and log token metrics
            input_tokens, output_tokens, total_tokens = extract_token_metrics(collector)
            span.set_attributes({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            })

            _logger.info(
                f"Tool assessment completed. "
                f"Used: {assessment.tool_was_used}, "
                f"Quality: {assessment.tool_usage_quality}, "
                f"Recommendation: {assessment.recommendation}"
            )

            return TrainingState.DECIDE_TOOL_FATE, context

        except Exception as e:
            _logger.error(f"Error assessing tool usage: {e}")
            context.error_message = f"Tool assessment error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context


def handle_decide_tool_fate(context: Context) -> Tuple[TrainingState, Context]:
    """
    Make final decision about whether to keep or discard the tested tool.

    This state processes the assessment results and implements the keep/discard decision,
    updating the tool registry accordingly.
    """
    from src.util import save_new_tool, get_created_tools

    with mlflow.start_span(name="DecideToolFate", span_type="CHAIN") as span:
        try:
            assessment = context.tool_assessment

            if not assessment:
                # No assessment available, conservative approach: keep the tool
                context.tool_saved = True
                decision_reason = "No assessment available - keeping tool conservatively"
                _logger.warning(f"No tool assessment available for {context.tool_name}, keeping conservatively")

            elif assessment.recommendation == "keep_tool":
                # Tool is helpful, keep it
                context.tool_saved = True
                decision_reason = assessment.usage_details
                _logger.info(f"✅ Tool {context.tool_name} validated and kept: {assessment.usage_details}")

            elif assessment.recommendation == "discard_tool":
                # Tool is not useful, don't save it permanently
                context.tool_saved = False
                decision_reason = assessment.usage_details
                _logger.info(f"❌ Tool {context.tool_name} discarded: {assessment.usage_details}")

            elif assessment.recommendation == "improve_tool":
                # Tool has potential but needs work - for now, don't save it
                context.tool_saved = False
                decision_reason = f"Tool needs improvement: {assessment.usage_details}"
                _logger.warning(f"⚠️ Tool {context.tool_name} needs improvement: {assessment.usage_details}")

            else:  # unclear
                # Unclear assessment - conservative: keep the tool
                context.tool_saved = True
                decision_reason = f"Assessment unclear, keeping conservatively: {assessment.usage_details}"
                _logger.info(f"❓ Tool {context.tool_name} assessment unclear, keeping tentatively")

            # Implement the decision
            if context.tool_saved:
                # Ensure tool is permanently saved (might have been only temporary)
                if context.path_taken == "correct":  # Path A: new tool
                    if context.create_tool_result and context.create_tool_result.success:
                        save_success = save_new_tool(
                            function_name=context.tool_name,
                            function_implementation=context.create_tool_result.function_implementation,
                        )
                        if not save_success:
                            _logger.error(f"Failed to permanently save tool: {context.tool_name}")
                            context.tool_saved = False
                            decision_reason += " (Save failed)"

                elif context.path_taken == "wrong":  # Path B: debugged tool
                    if context.debug_tool_result and context.debug_tool_result.success:
                        save_success = save_new_tool(
                            function_name=context.tool_name,
                            function_implementation=context.debug_tool_result.fixed_implementation,
                        )
                        if not save_success:
                            _logger.error(f"Failed to permanently save debugged tool: {context.tool_name}")
                            context.tool_saved = False
                            decision_reason += " (Save failed)"

            # Log decision to MLflow
            span.set_outputs({
                "tool_saved": context.tool_saved,
                "recommendation": assessment.recommendation if assessment else "no_assessment",
                "tool_was_used": assessment.tool_was_used if assessment else False,
                "tool_usage_quality": assessment.tool_usage_quality if assessment else "unknown",
                "confidence": assessment.confidence if assessment else "low",
                "decision_reason": decision_reason,
                "path_taken": context.path_taken,
            })

            _logger.info(
                f"Tool fate decision completed for {context.tool_name}: "
                f"{'KEPT' if context.tool_saved else 'DISCARDED'} "
                f"(recommendation: {assessment.recommendation if assessment else 'none'})"
            )

            return TrainingState.END, context

        except Exception as e:
            _logger.error(f"Error deciding tool fate: {e}")
            context.error_message = f"Tool fate decision error: {e}"
            span.set_status("ERROR")
            return TrainingState.ERROR, context
```

#### 4.4 Updated Existing Handlers

```python
def handle_create_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Create a new helper function (Path A: Correct answer).

    Updated to proceed to tool testing instead of immediate saving.
    """
    # ... existing implementation up to result creation ...

    if result.success:
        # Don't save immediately - proceed to testing first
        _logger.info(f"New tool created for testing: {context.tool_name}")

        # Temporarily add the tool to available tools for testing
        # (but don't permanently save yet)
        try:
            import importlib.util
            import sys

            # Create module from function implementation
            spec = importlib.util.spec_from_loader("temp_tool", loader=None)
            temp_module = importlib.util.module_from_spec(spec)

            # Execute the function code to add it to the module
            exec(result.function_implementation, temp_module.__dict__)

            # Add the function to available tools
            context.tools[context.tool_name] = getattr(temp_module, context.tool_name)

        except Exception as e:
            _logger.error(f"Failed to load new tool for testing: {e}")
            context.error_message = f"Tool loading error: {e}"
            return TrainingState.ERROR, context

        context.create_tool_result = result
        # Note: tool_saved remains False until after testing

        return TrainingState.TEST_TOOL_WITH_COBBIE, context
    else:
        _logger.warning(f"Tool creation failed: {result.thoughts}")
        context.error_message = f"Tool creation failed: {result.thoughts}"
        return TrainingState.ERROR, context


def handle_debug_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Debug and fix a faulty helper function (Path B: Wrong answer).

    Updated to proceed to tool testing instead of immediate saving.
    """
    # ... existing implementation up to result creation ...

    if result.success:
        # Don't save immediately - proceed to testing first
        _logger.info(f"Faulty tool debugged for testing: {context.tool_name}")

        # Temporarily add the debugged function to available tools
        try:
            import importlib.util

            spec = importlib.util.spec_from_loader("temp_tool", loader=None)
            temp_module = importlib.util.module_from_spec(spec)

            exec(result.fixed_implementation, temp_module.__dict__)
            context.tools[context.tool_name] = getattr(temp_module, context.tool_name)

        except Exception as e:
            _logger.error(f"Failed to load debugged tool for testing: {e}")
            context.error_message = f"Debugged tool loading error: {e}"
            return TrainingState.ERROR, context

        context.debug_tool_result = result
        # Note: tool_saved remains False until after testing

        return TrainingState.TEST_TOOL_WITH_COBBIE, context
    else:
        _logger.warning(f"Tool debugging failed: {result.thoughts}")
        context.error_message = f"Tool debugging failed: {result.thoughts}"
        return TrainingState.ERROR, context
```

#### 4.5 Updated Process State Dispatcher

```python
def process_state(state: TrainingState, context: Context) -> Tuple[TrainingState, Context]:
    """
    Process the current training state and return the next state.
    """
    if state == TrainingState.START:
        return handle_start_state(context)
    elif state == TrainingState.RUN_COBBIE:
        return handle_run_cobbie(context)
    elif state == TrainingState.VERIFY_ANSWER:
        return handle_verify_answer(context)
    elif state == TrainingState.IDENTIFY_NEW_TOOL:
        return handle_identify_new_tool(context)
    elif state == TrainingState.CREATE_NEW_TOOL:
        return handle_create_new_tool(context)
    elif state == TrainingState.IDENTIFY_FAULTY_TOOL:
        return handle_identify_faulty_tool(context)
    elif state == TrainingState.DEBUG_FAULTY_TOOL:
        return handle_debug_faulty_tool(context)
    elif state == TrainingState.TEST_TOOL_WITH_COBBIE:
        return handle_test_tool_with_cobbie(context)
    elif state == TrainingState.ASSESS_TOOL_USAGE:
        return handle_assess_tool_usage(context)
    elif state == TrainingState.DECIDE_TOOL_FATE:
        return handle_decide_tool_fate(context)
    elif state == TrainingState.END:
        return TrainingState.END, context
    elif state == TrainingState.ERROR:
        return TrainingState.ERROR, context
    else:
        raise ValueError(f"Unknown state: {state}")
```

---

## 5. Export Updates

### File: `src/agents/__init__.py`

```python
# Add to existing exports
from .assess_helper_function import assess_helper_function

# Update __all__ list
__all__ = [
    "cobbie",
    "verify_answer",
    "identify_helper_function",
    "create_helper_function",
    "identify_faulty_tool",
    "debug_helper_function",
    "assess_helper_function",  # New
]
```

---

## 6. Integration Points and Considerations

### 6.1 MLflow Integration

The implementation includes comprehensive MLflow tracking at multiple levels:

1. **Agent-level tracking**: Individual agent spans for token usage and duration
2. **State-level tracking**: Each state handler creates its own span
3. **Tool-level metrics**: Specific metrics for tool usage and assessment
4. **Decision tracking**: Final tool fate decisions are logged

### 6.2 Error Handling

1. **Graceful degradation**: If assessment fails, tools are kept conservatively
2. **Comprehensive logging**: All errors are logged with context
3. **Span status**: MLflow spans properly reflect error states
4. **Recovery paths**: Error states don't crash the entire training run

### 6.3 Performance Considerations

1. **Token usage**: Assessment is lightweight compared to full Cobbie re-run
2. **Execution time**: One additional Cobbie run per tool creation/debug
3. **Memory usage**: Temporary tools are properly managed
4. **Cost efficiency**: Avoids dedicated testing infrastructure

### 6.4 Configuration Options

The design allows for future configuration:

```python
# Future configuration options
class ToolValidationConfig:
    enable_enhanced_questions: bool = True
    assessment_threshold_confidence: str = "medium"  # "low", "medium", "high"
    auto_discard_unclear: bool = False  # Conservative: keep unclear assessments
    max_testing_iterations: int = 10
```

---

## 7. Testing Strategy

### 7.1 Unit Testing

1. **AssessHelperFunction BAML tests**: All three test cases implemented
2. **Python agent tests**: Mock inputs and verify outputs
3. **State handler tests**: Test state transitions and decisions
4. **Schema validation**: Verify ToolUsageAnalysis field constraints

### 7.2 Integration Testing

1. **End-to-end training runs**: Small dataset with tool creation
2. **Tool lifecycle testing**: Verify temporary → permanent flow
3. **MLflow tracking**: Confirm proper span hierarchy and metrics
4. **Error scenarios**: Test graceful degradation paths

### 7.3 Performance Testing

1. **Token usage measurement**: Compare with and without validation
2. **Execution time profiling**: Measure additional overhead
3. **Memory usage monitoring**: Ensure no leaks with temporary tools
4. **Cost analysis**: Track LLM usage costs

---

## 8. Success Criteria

The implementation is successful when:

### Functional Requirements
- ✅ Tools are tested with guided Cobbie execution
- ✅ Usage assessment provides meaningful feedback
- ✅ Keep/discard decisions are implemented correctly
- ✅ State machine flows smoothly through new validation states
- ✅ Error handling is robust and non-disruptive

### Quality Requirements
- ✅ Assessment confidence levels are appropriate
- ✅ False positive/negative rates are acceptable
- ✅ Token usage is optimized for assessment
- ✅ Tool recommendations are actionable

### Integration Requirements
- ✅ MLflow tracking provides comprehensive visibility
- ✅ Existing training workflow is not disrupted
- ✅ Backward compatibility is maintained
- ✅ Configuration options allow tuning

---

## 9. Future Enhancements

### 9.1 Multiple Question Testing

For improved tool validation:

```python
# Future: Test tool across multiple similar questions
def test_tool_across_questions(
    tool_name: str,
    tool_implementation: str,
    similar_questions: List[Tuple[str, str]]  # (question, ground_truth)
) -> MultiQuestionToolAssessment:
    # Test tool on multiple related questions
    # Aggregate results across different scenarios
    # Provide more robust validation
```

### 9.2 Automated Tool Comparison

```python
# Future: Compare tool performance with and without new tool
def compare_tool_performance(
    original_execution: str,
    enhanced_execution: str,
    tool_name: str
) -> ToolPerformanceComparison:
    # Direct comparison of execution efficiency
    # Measure improvements in accuracy or speed
    # Quantify tool's specific contribution
```

### 9.3 Tool Quality Metrics

```python
# Future: Comprehensive tool quality scoring
def calculate_tool_quality_score(
    usage_assessment: ToolUsageAnalysis,
    execution_metrics: dict,
    error_rate: float
) -> ToolQualityScore:
    # Multi-factor scoring system
    - Usage frequency
    - Correctness contribution
    - Performance impact
    - Error robustness
```

---

## 10. Implementation Timeline

### Phase 1: Core Implementation (Estimated 2-3 days)
1. **Day 1**: Schema and BAML function implementation
2. **Day 2**: Python agent implementation and basic testing
3. **Day 3**: State machine integration and MLflow tracking

### Phase 2: Integration and Testing (Estimated 1-2 days)
1. **Day 4**: Export updates and agent registration
2. **Day 5**: Integration testing with training workflow
3. **Day 6**: Performance testing and optimization

### Phase 3: Validation and Documentation (Estimated 1 day)
1. **Day 7**: End-to-end testing and documentation updates
2. **Buffer day**: Additional testing and refinements

---

## 11. Dependencies and Prerequisites

### Required Components
- ✅ Existing agent infrastructure (`src/agents/`)
- ✅ BAML framework integration (`baml_src/`)
- ✅ Training phase scaffolding (`scripts/run_training_phase.py`)
- ✅ MLflow tracking infrastructure
- ✅ Tool management utilities (`src/engine/util/`)

### External Dependencies
- ✅ All current dependencies (no new ones required)
- ✅ MLflow server for tracking
- ✅ LLM providers (Z.AI, OpenAI, etc.)

---

## Conclusion

This enhanced tool validation approach provides a **balanced solution** that:

1. **Validates tools in real context** - Tests tools in actual usage scenarios
2. **Provides targeted feedback** - Gives specific tool utility assessments
3. **Maintains simplicity** - Reuses existing infrastructure without major complexity
4. **Enables informed decisions** - Data-driven keep/discard choices
5. **Supports future enhancements** - Extensible architecture for advanced testing

The implementation follows established patterns in the codebase while adding sophisticated tool validation capabilities that will improve the quality and reliability of the helper function ecosystem during training.
