# Agent Implementation Guidelines

This document outlines best practices for implementing BAML agents in the Cobbie system, based on established patterns from existing implementations.

## Table of Contents
1. [MLflow Logging Patterns](#mlflow-logging-patterns)
2. [Error Handling Strategy](#error-handling-strategy)
3. [Control Flow Management](#control-flow-management)
4. [Token & Trajectory Tracking](#token--trajectory-tracking)

## MLflow Logging Patterns

### Span Hierarchy Structure

All agents follow a consistent 3-level span hierarchy:

```python
# Level 1: Run context (create if not exists)
active_run = mlflow.active_run()
run_context_manager = (
    nullcontext()
    if active_run
    else mlflow.start_run(run_name="AgentName")
)

with run_context_manager:
    # Level 2: Main agent span (CHAIN type)
    with mlflow.start_span(name="AgentName", span_type="CHAIN") as agent_span:
        # Level 3: LLM call spans (LLM type)
        with mlflow.start_span(name="LLM_call_1", span_type="LLM") as llm_span:
```

### Standard Logging Content

**Always log these parameters:**
```python
mlflow.log_params({
    "component": "AgentName",
    "llm_provider": llm_provider,
    "llm_model": llm_name,
})
```

**Always log these metrics:**
```python
mlflow.log_metrics({
    "agent_input_tokens": input_tokens,
    "agent_output_tokens": output_tokens,
    "agent_total_tokens": total_tokens,
    "agent_execution_time": execution_time,
    "agent_success": 1 if result.success else 0,
})
```

**Span inputs always include:**
- Core function parameters
- Execution context (max_iterations, previous_attempts, etc.)

**Span outputs always include:**
- Primary result data
- Success/failure status
- Execution history/context

**Span attributes always include:**
- Token usage breakdown
- Execution time
- Provider/model info
- Call counts

### Iterative Agent Pattern

For complex agents (like `cobbie.py`), use nested iteration spans:

```python
for iteration in range(max_iterations):
    with mlflow.start_span(name=f"Iteration_{iteration + 1}", span_type="CHAIN") as iteration_span:
        with mlflow.start_span(name=f"LLM_call_{iteration + 1}", span_type="LLM") as llm_span:
            # BAML call and iteration logic
```

**Reference implementation:** `src/agents/cobbie.py:95-120`

## Error Handling Strategy

### Try-Except Block Placement

**Rule:** Wrap ALL BAML calls in try-except blocks:

```python
def agent_function(**kwargs) -> Tuple[ResultType, Collector]:
    collector = Collector(name="AgentName")

    with mlflow.start_span(name="Agent", span_type="LLM") as span:
        try:
            result = b.with_options(**kwargs).BAMLFunction(
                param1=value1,
                param2=value2,
            )

            # Success logging
            span.set_outputs({
                "result_type": type(result).__name__,
                "success": True,
                "result": result,
            })

        except Exception as e:
            # Create meaningful fallback
            fallback_result = ResultType(
                thoughts=f"An Exception occurred: {e}",
                success=False,
                # ... other fallback fields
            )

            # Error logging
            span.set_outputs({
                "error": str(e),
                "fallback_result": fallback_result,
                "success": False,
            })

            span.set_attributes({
                "error_occurred": True,
                "error_type": type(e).__name__,
            })

            return fallback_result, collector
```

**Reference implementation:** `src/agents/answer_verifier.py:85-115`

### Fallback Result Pattern

Always create meaningful fallback results that maintain the expected return type structure:

```python
# Example fallback for AnswerVerifier
fallback_result = Answer(
    thoughts=f"An Exception occurred: {e}",
    answer="Error: Unable to process request",
    success=False,
)
```

## Control Flow Management

### Union Type Handling

All agents use union return types with consistent flow control:

```python
def agent_function(**kwargs) -> Tuple[ResultType, Collector, str]:
    try:
        result = b.with_options(**kwargs).BAMLFunction(...)

        # Handle union types
        if isinstance(result, ExpectedResultType):
            return result, collector, execution_history
        elif isinstance(result, CodeAction):
            # Handle action (for iterative agents)
            action_result = execute_code(result)
            # Continue loop...
        else:
            # Handle unexpected types
            error_msg = f"Unexpected result type: {type(result)}"
            # Create fallback and continue...

    except Exception as e:
        # Error handling as shown above
```

**Reference implementation:** `src/agents/create_helper_function.py:150-180`

### Iterative Loop Pattern

For agents that need multiple iterations:

```python
def _agent_with_loop(max_iterations: int = 15, **kwargs) -> Tuple[ResultType, str]:
    previous_attempts = ""

    for iteration in range(max_iterations):
        # Single iteration
        result = _single_iteration(previous_attempts, **kwargs)

        # Check result type
        if isinstance(result, FinalResultType):
            return result, previous_attempts
        elif isinstance(result, CodeAction):
            # Execute action and continue
            execution_result = _execute_code_action(result, iteration, tools)
            previous_attempts += f"\n{execution_result}\n"
            continue
        else:
            # Handle unexpected result
            previous_attempts += f"\nError: Unexpected result type {type(result)}"
            continue
```

**Reference implementation:** `src/agents/cobbie.py:200-250`

## Token & Trajectory Tracking

### Collector Integration Pattern

All agents must integrate collectors for token tracking:

```python
def agent_function(**kwargs) -> Tuple[ResultType, Collector, str]:
    # Create collector
    collector = Collector(name="AgentName")

    # Add collector to BAML options
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    # Execute logic...
    result, execution_history = _core_logic(**kwargs)

    # Extract token usage safely
    input_tokens, output_tokens, total_tokens = _extract_token_metrics(collector)

    return result, collector, execution_history


def _extract_token_metrics(collector: Optional[Collector]) -> Tuple[int, int, int]:
    """Safely extract token metrics from collector."""
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

**Reference implementation:** `src/agents/qa_pair_aligner.py:60-90`

### Execution History Management

Maintain execution history for context across iterations:

```python
# Initialize history
previous_attempts = ""

# After each iteration/action
current_attempt = _execute_action(result, iteration, tools)
previous_attempts += f"\n{current_attempt}\n"

# Pass to next iteration
result = b.BAMLFunction(
    previous_attempts=previous_attempts,
    # ... other params
)
```

**Reference implementation:** `src/agents/identify_helper_function.py:140-170`

### Comprehensive Token Metrics

Always log comprehensive token information:

```python
# Span attributes
span.set_attributes({
    "token_usage.input_tokens": input_tokens,
    "token_usage.output_tokens": output_tokens,
    "token_usage.total_tokens": total_tokens,
    "execution_time_seconds": execution_time,
    "collector.calls_count": len(collector.logs) if collector and hasattr(collector, "logs") else 0,
})

# MLflow metrics
mlflow.log_metrics({
    "agent_input_tokens": input_tokens,
    "agent_output_tokens": output_tokens,
    "agent_total_tokens": total_tokens,
})
```

## Testing Pattern

### Self-Contained Tests in `if __main__` Block

For agents that analyze other agents' outputs, create realistic test workflows:

```python
if __name__ == "__main__":
    # 1. Run the upstream agent (e.g., cobbie)
    result, collector, history = upstream_agent(...)
    
    # 2. Verify/process results (e.g., answer_verifier)
    verification, v_collector = verify_agent(...)
    
    # 3. Analyze with your agent (conditional on step 2)
    if verification.classification == "wrong":
        analysis, a_collector = your_agent(
            history=history,
            result=result,
            ...
        )
        # Display results and metrics
```

**Reference implementations:** 
- `src/agents/identify_helper_function.py:123-195` (for successful executions)
- `src/agents/faulty_tool_identifier.py:143-284` (for failed executions)

## Quick Reference Examples

### Simple Agent Template
**Files:** `src/agents/answer_verifier.py`, `src/agents/identify_helper_function.py`

### Complex Agent Template
**File:** `src/agents/cobbie.py` (lines 50-150)

### BAML Template Structure
**Directory:** `baml_src/` - see any `.baml` file for consistent prompt structure

## Key Takeaways

1. **Always** use the 3-level span hierarchy
2. **Always** wrap BAML calls in try-except blocks
3. **Always** create meaningful fallback results
4. **Always** integrate collectors for token tracking
5. **Always** extract token metrics safely
6. **Always** maintain execution history for context
7. **Always** log standardized inputs/outputs/attributes

Following these patterns ensures consistent logging, robust error handling, and comprehensive tracking across all agents in the system.
