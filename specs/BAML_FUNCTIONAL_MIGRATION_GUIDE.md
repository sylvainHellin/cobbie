# BAML Functional Migration Guide

This guide provides patterns and best practices for converting OOP DSPy agents to functional BAML approach, with integrated MLflow tracing and metrics tracking.

## 🎯 Quick Reference: Required Patterns

**Every migrated agent MUST follow this pattern:**

1. **Three Functions (Advanced)**: Create `function_name()`, `function_name_with_metrics()`, and optionally `function_name_forward()` for compatibility
2. **MLflow Parameter**: The `_with_metrics` function always has `mlflow: bool = True`
3. **Return Types**: Base function returns `ResultType`, metrics function returns `Tuple[ResultType, LM_Metrics]`
4. **Configuration**: Most config goes in `.baml` files, with runtime overrides via `ClientRegistry`
5. **⚠️ Token Tracking**: Use `collector.usage` for cumulative totals, `collector.last.usage` only for single calls
6. **🆕 Nested Spans**: Implement 3-level span hierarchy for complex systems (main → iteration → LLM calls)
7. **🆕 Context Management**: Use `nullcontext()` pattern to handle existing MLflow runs gracefully

**Example Template (Advanced 3-Function Pattern):**
```python
def my_function(param1: str, param2: Optional[str] = None) -> ResultType:
    """Base function - no MLflow orchestration."""
    # Direct functional implementation without MLflow orchestration
    pass

def my_function_with_metrics(
    param1: str,
    param2: Optional[str] = None,
    mlflow: bool = True  # ALWAYS REQUIRED
) -> Tuple[ResultType, LM_Metrics]:
    """Function with MLflow orchestration and metrics."""
    # ✅ CRITICAL: Use cumulative token tracking
    if collector and hasattr(collector, 'usage') and collector.usage:
        usage = collector.usage  # All calls, not just last!
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0

    # Implementation with comprehensive MLflow spans and LM_Metrics return
    pass

def my_function_forward(
    param1: str,
    param2: Optional[str] = None,
    config: Optional[ConfigType] = None
) -> ModuleOutput:
    """
    Backward compatibility wrapper returning ModuleOutput.

    Provides compatibility with existing interfaces while using new functional implementation.
    """
    # Convert between ResultType and ModuleOutput for compatibility
    result = my_function(param1, param2)
    return _result_to_module_output(result)
```

## Table of Contents

1. [Quick Reference: Context7 Library IDs](#quick-reference-context7-library-ids)
2. [Architecture Overview](#architecture-overview)
3. [Pattern Conversion: Class → Function](#pattern-conversion-class--function)
4. [MLflow Integration Patterns](#mlflow-integration-patterns)
5. [Token Usage & Metrics Tracking](#token-usage--metrics-tracking)
6. [Essential Code Patterns](#essential-code-patterns)
7. [Migration Checklist](#migration-checklist)

## Quick Reference: Context7 Library IDs

For fast lookups and latest syntax, use these Context7 library IDs:

- **BAML**: `/boundaryml/baml` (Trust Score: 7.7, 1189 code snippets)
- **MLflow**: `/mlflow/mlflow` (Trust Score: 9.1, 3114 code snippets)

Usage example:
```python
# In Claude Code, use Context7 to get latest docs
/context7 resolve-library-id baml
/context7 get-library-docs /boundaryml/baml --topic "collector python"
```

## Architecture Overview

### Why Functional BAML?

**Key Benefits over OOP DSPy:**
- **Enhanced Observability**: Comprehensive MLflow spans with actual parameters vs minimal DSPy logging
- **Clean Flow Control**: Union types (`CodeAction | ResultType`) vs complex state management
- **Direct Token Tracking**: BAML Collector API vs manual extraction from `lm.history`
- **Improved Performance**: Reduced iterations and cleaner execution patterns
- **Better Error Handling**: Functional patterns with comprehensive logging

### Reference Implementation

**🆕 Canonical Reference Implementation:**
See `src/engine/components/cobbie.py` for the complete production-quality advanced implementation of these patterns.

**COBBIE** demonstrates:
- **Advanced 3-Function Architecture**: `cobbie()`, `cobbie_with_metrics()`, `cobbie_forward()`
- **Sophisticated MLflow Integration**: 3-level nested span hierarchy with comprehensive tracking
- **Advanced Token Monitoring**: Dual-level token tracking with both cumulative and per-iteration metrics
- **Comprehensive Error Handling**: Per-iteration error classification with severity-based flow control
- **Production-Quality Patterns**: Real-world implementation that powers the BAML engine

**Simple Component Reference**: See `src/engine/components/baml_answer_verifier.py` for basic 2-function pattern implementation.

## Pattern Conversion: Class → Function

### Advanced Function Pattern (REQUIRED)

**Every complex agent SHOULD follow this three-function pattern:**

1. **Base Function**: Simple function returning just the result
2. **Function with Metrics**: Returns tuple of `(result, LM_Metrics)` with comprehensive MLflow support
3. **Compatibility Wrapper**: Returns existing interface types (e.g., `ModuleOutput`) for backward compatibility

**When to use which pattern:**
- **Simple Components**: 2-function pattern is sufficient (e.g., AnswerVerifier)
- **Complex Systems**: 3-function pattern recommended (e.g., COBBIE, TestAndImprove)
- **Interface Migration**: Always include compatibility wrapper when replacing existing components

**DSPy OOP Pattern:**
```python
class AnswerVerifier(dspy.Module):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or AGENT_CONFIGS.answer_verifier
        self.lm = self.config.llm.get_llm()

    def forward(self, question, category, ground_truth, system_response, bim_context=None):
        with dspy.context(lm=self.lm, adapter=self.config.llm.adapter):
            # Implementation
            pass
```

**BAML Functional Pattern (Advanced 3-Function):**
```python
def verify_answer(
    question: str,
    category: Literal[1, 2, 3, 4],
    ground_truth: str,
    system_response: str,
    bim_context: Optional[str] = "BIM model containing building information"
) -> AnswerEvaluationResult:
    """Base function - returns only the result."""
    # Direct functional implementation without MLflow orchestration
    baml_result, collector = run_baml_function_with_metrics(
        component_name="AnswerVerifier",
        baml_function=b.EvaluateResponse,
        question=question,
        category=_map_category_to_baml(category),
        ground_truth=ground_truth,
        system_response=system_response,
        bim_context=bim_context
    )
    return baml_result


def verify_answer_with_metrics(
    question: str,
    category: Literal[1, 2, 3, 4],
    ground_truth: str,
    system_response: str,
    bim_context: Optional[str] = "BIM model containing building information",
    mlflow: bool = True  # ALWAYS include this parameter
) -> Tuple[AnswerEvaluationResult, LM_Metrics]:
    """Function with metrics - includes MLflow orchestration and returns LM_Metrics."""
    # Implementation with comprehensive MLflow spans and metrics collection
    # (See MLflow Integration Patterns section for full implementation)


def verify_answer_forward(
    question: str,
    category: Literal[1, 2, 3, 4],
    ground_truth: str,
    system_response: str,
    bim_context: Optional[str] = "BIM model containing building information",
    config: Optional[ConfigType] = None
) -> ModuleOutput:
    """
    Backward compatibility wrapper returning ModuleOutput.

    This function provides compatibility with the existing interface while using
    the new functional implementation. Can be removed when all calling code
    is updated to use the new interface directly.
    """
    try:
        final_answer = verify_answer(
            question=question,
            category=category,
            ground_truth=ground_truth,
            system_response=system_response,
            bim_context=bim_context
        )

        # Convert AnswerEvaluationResult to ModuleOutput for compatibility
        return _answer_result_to_module_output(final_answer)

    except Exception as e:
        # Handle errors gracefully
        logger.error(f"Error in verify_answer_forward: {e}")
        output = ModuleOutput()
        output.status = "error"
        output.error_msg = f"Answer verification failed: {str(e)}"
        return output
```

### Configuration Handling

**With BAML, most configuration is handled in `.baml` files:**

```baml
// In your .baml schema file
client<llm> MyClient {
  provider "openai"
  options {
    api_key env.OPENAI_API_KEY
    model "gpt-4"
    temperature 0.1
  }
}

// Or use client registry for runtime configuration
client<llm> ConfigurableClient {
  provider openai
  options {
    model "gpt-4"
    // Can be overridden at runtime
  }
}
```

**Runtime Configuration Override (when needed):**
```python
from baml_py import ClientRegistry

def function_with_runtime_config():
    # Override configuration at runtime
    client_registry = ClientRegistry()
    client_registry.add_llm_client(
        name='MyTempClient',
        provider='openai',
        options={
            "model": "gpt-4-turbo",
            "temperature": 0.2,
            "api_key": os.environ.get('OPENAI_API_KEY')
        }
    )
    client_registry.set_primary('MyTempClient')

    result, collector = run_baml_function_with_metrics(
        component_name="ComponentName",
        baml_function=b.MyFunction,
        input_data=data,
        client_registry=client_registry  # Pass runtime config
    )
    return result
```

**Legacy Configuration Handling (if still needed):**
```python
# For remaining non-BAML configuration
from src.config import AGENT_CONFIGS

def function_with_legacy_config(param: str, config: Optional[ConfigType] = None):
    effective_config = config or AGENT_CONFIGS.default_config
    # Use effective_config for any remaining non-BAML parameters
```

## MLflow Integration Patterns

### Context Manager Best Practices

**🆕 Advanced Multi-Level Span Pattern (COBBIE-style):**
```python
import mlflow
from contextlib import nullcontext

def complex_function_with_metrics(..., mlflow: bool = True):
    if mlflow:
        # Check if we're already in an MLflow run
        active_run = mlflow.active_run()
        run_context_manager = (
            nullcontext()
            if active_run
            else mlflow.start_run(run_name="ComplexFunction_Execution_Run")
        )

        with run_context_manager:
            # Log comprehensive parameters following run_evaluation.py pattern
            mlflow.log_params({
                "component": "ComplexFunction",
                "engine_type": "baml",
                "max_iterations": max_iterations,
                "tools_count": len(tools),
                "llm_provider": llm_provider,
                "llm_model": llm_name,
                "tools": ", ".join(tools.keys()),
            })

            # Main execution span
            with mlflow.start_span(name="ComplexFunction", span_type="CHAIN") as main_span:
                main_span.set_inputs({
                    "user_input": user_input,
                    "max_iterations": max_iterations,
                    "tools_count": len(tools),
                })

                # Multi-iteration loop with per-iteration spans
                for iteration in range(max_iterations):
                    with mlflow.start_span(
                        name=f"Iteration_{iteration + 1}", span_type="CHAIN"
                    ) as iteration_span:

                        # LLM call span within iteration
                        with mlflow.start_span(
                            name=f"LLM_call_{iteration + 1}", span_type="LLM"
                        ) as llm_span:
                            llm_span.set_inputs({
                                "question": question,
                                "iteration": iteration + 1,
                            })

                            # BAML function call
                            result, collector = run_baml_function_with_metrics(...)

                            # Extract token usage (cumulative for multi-call systems)
                            input_tokens = 0
                            output_tokens = 0
                            if collector and hasattr(collector, 'usage') and collector.usage:
                                usage = collector.usage
                                input_tokens = usage.input_tokens or 0
                                output_tokens = usage.output_tokens or 0

                            llm_span.set_attributes({
                                "llm.provider": llm_provider,
                                "llm.model": llm_name,
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "total_tokens": input_tokens + output_tokens,
                            })

                            llm_span.set_outputs({
                                "result_type": type(result).__name__,
                                "iteration": iteration + 1,
                            })

                        # Handle iteration result
                        if isinstance(result, FinalResult):
                            iteration_span.set_outputs({
                                "final_answer": result.answer,
                                "total_iterations": iteration + 1,
                                "iteration_success": True,
                            })
                            iteration_span.set_status("OK")

                            # Set main span outputs and return
                            main_span.set_outputs({
                                "answer": result.answer,
                                "total_iterations": iteration + 1,
                                "success": True,
                            })
                            main_span.set_status("OK")
                            return result, metrics

                        elif isinstance(result, CodeAction):
                            # Continue to next iteration
                            iteration_span.set_status("OK")
                            continue

                        else:
                            # Handle unexpected result type
                            error_msg = f"Unexpected result type: {type(result)}"
                            iteration_span.set_outputs({"error_msg": error_msg})
                            iteration_span.set_status("ERROR")
                            continue

                # Max iterations reached
                main_span.set_outputs({
                    "termination_reason": "max_iterations_reached",
                    "total_iterations": max_iterations,
                    "success": False,
                })
                main_span.set_status("OK")

                # Create final incomplete result
                final_result = create_incomplete_result(...)
                return final_result, metrics

    else:
        # Run without MLflow orchestration
        return direct_function_call(...)
```

**Standard Span Pattern (for simple components):**
```python
def verify_answer_with_metrics(..., mlflow: bool = True):
    if mlflow:
        with mlflow.start_span(name="BamlAnswerVerifier", span_type="CHAIN") as verifier_span:
            verifier_span.set_inputs({
                "question": question,
                "category": category,
                "ground_truth": ground_truth,
                "system_response": system_response,
                "bim_context": bim_context
            })

            try:
                # BAML function call
                result, collector = run_baml_function_with_metrics(...)

                verifier_span.set_outputs({
                    "classification": result.classification,
                    "justification": result.justification,
                    "confidence": result.confidence,
                    "input_tokens": collector.last.usage.input_tokens if collector.last else 0,
                    "output_tokens": collector.last.usage.output_tokens if collector.last else 0,
                    "status": "success"
                })
                verifier_span.set_status("OK")

                return result, metrics

            except Exception as e:
                verifier_span.set_outputs({
                    "error": str(e),
                    "status": "error"
                })
                verifier_span.set_status("ERROR")
                raise
    else:
        # Run without MLflow orchestration span
        return direct_function_call(...)
```

### Span Hierarchy Standards

**Nested Span Pattern:**
```python
with mlflow.start_span(name="Component_Name", span_type="CHAIN") as component_span:
    component_span.set_inputs({
        "param1": value1,
        "param2": value2
    })
    component_span.set_attributes({
        "component": "ComponentName",
        "model_path": path_ifc_model or "no_model",
        "question_id": question_id,
        # add all useful attributes
    })

    # BAML function calls automatically create nested spans
    result, collector = run_baml_function_with_metrics(
        component_name="SubComponent",
        baml_function=b.BamlFunction,
        ...
    )

    component_span.set_outputs({
        "status": "success",
        "result_summary": summarize_result(result)
    })
```

### Error Handling Patterns

**🆕 Advanced Per-Iteration Error Handling (COBBIE Pattern):**
```python
def robust_multi_iteration_function(...):
    """
    Comprehensive error handling with per-iteration status management.

    Each iteration gets granular error tracking with appropriate span status.
    """
    # Initialize error tracking
    error_count = 0
    critical_errors = []

    for iteration in range(max_iterations):
        with mlflow.start_span(
            name=f"Iteration_{iteration + 1}", span_type="CHAIN"
        ) as iteration_span:

            try:
                # Main processing logic
                result = process_iteration(iteration, previous_attempts)

                # Handle successful result
                if isinstance(result, FinalResult):
                    iteration_span.set_outputs({
                        "final_answer": result.answer,
                        "total_iterations": iteration + 1,
                        "error_count": error_count,
                        "iteration_success": True,
                    })
                    iteration_span.set_status("OK")
                    return result

                # Continue for intermediate results
                iteration_span.set_status("OK")
                continue

            except Exception as e:
                error_count += 1
                error_type = type(e).__name__
                error_message = str(e)

                # 🆕 Granular error classification
                if "token" in error_message.lower():
                    error_category = "token_limit"
                    severity = "warning"
                elif "timeout" in error_message.lower():
                    error_category = "timeout"
                    severity = "error"
                elif "permission" in error_message.lower():
                    error_category = "permission"
                    severity = "critical"
                else:
                    error_category = "unknown"
                    severity = "error"

                # 🆕 Track critical errors separately
                if severity == "critical":
                    critical_errors.append({
                        "iteration": iteration + 1,
                        "error_type": error_type,
                        "error_message": error_message,
                        "category": error_category
                    })

                # Set iteration span with comprehensive error information
                iteration_span.set_outputs({
                    "error_type": error_type,
                    "error_message": error_message,
                    "error_category": error_category,
                    "error_severity": severity,
                    "error_count": error_count,
                    "iteration": iteration + 1,
                })

                iteration_span.set_attributes({
                    "error.occurred": True,
                    "error.category": error_category,
                    "error.severity": severity,
                    "error.count.total": error_count,
                    "error.count.critical": len(critical_errors),
                })

                iteration_span.set_status("ERROR")

                # 🆕 Decide whether to continue or abort based on severity
                if severity == "critical":
                    logger.error(f"Critical error in iteration {iteration + 1}: {e}")
                    break
                else:
                    logger.warning(f"Non-critical error in iteration {iteration + 1}: {e}")
                    continue

    # Handle max iterations or critical errors
    with mlflow.start_span(
        name="Process_Completed_With_Errors", span_type="CHAIN"
    ) as final_span:
        final_span.set_inputs({
            "max_iterations": max_iterations,
            "total_errors": error_count,
            "critical_errors": len(critical_errors),
            "completion_reason": "max_iterations_or_critical_error"
        })

        if critical_errors:
            # Create result with critical error information
            final_answer = create_error_result(
                errors=critical_errors,
                total_iterations=max_iterations,
                error_summary=f"Process failed with {len(critical_errors)} critical errors"
            )
        else:
            # Create result with non-critical error information
            final_answer = create_partial_result(
                total_iterations=max_iterations,
                error_count=error_count,
                last_attempts=previous_attempts[-3:]  # Last 3 attempts
            )

        final_span.set_outputs({
            "answer": final_answer.answer,
            "reasoning": final_answer.thoughts,
            "total_errors": error_count,
            "critical_errors": len(critical_errors),
            "completion_status": "incomplete_with_errors"
        })

        final_span.set_status("OK")
        return final_answer
```

**Standard Error Handling (for simple components):**
```python
def robust_function(...):
    if mlflow:
        with mlflow.start_span(name="FunctionName", span_type="CHAIN") as span:
            span.set_inputs(inputs)

            try:
                result, collector = run_baml_function_with_metrics(...)

                span.set_outputs({
                    "status": "success",
                    **format_outputs(result)
                })
                span.set_status("OK")

                return result, metrics

            except Exception as e:
                error_details = {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "status": "error"
                }

                span.set_outputs(error_details)
                span.set_status("ERROR")

                logger.error(f"Function failed: {e}")
                raise
```

**🆕 Unexpected Result Type Handling:**
```python
def handle_unexpected_result_types(result, iteration):
    """
    Graceful handling of unexpected BAML result types.

    Maintains system stability when encountering unexpected union type members.
    """
    if isinstance(result, ExpectedType):
        return process_expected_result(result)

    elif isinstance(result, AnotherExpectedType):
        return process_alternative_result(result)

    else:
        # 🆕 Comprehensive unexpected type handling
        error_msg = f"Unexpected result type: {type(result)}"
        logger.error(error_msg)

        # Log detailed information about unexpected type
        logger.debug(f"Unexpected result details: {result}")
        logger.debug(f"Result attributes: {dir(result) if hasattr(result, '__dict__') else 'N/A'}")

        # Create safe fallback result
        fallback_result = create_safe_fallback_result(
            error_message=error_msg,
            iteration=iteration,
            result_type=type(result).__name__
        )

        return fallback_result
```

## Token Usage & Metrics Tracking

### BAML Collector API Usage

**⚠️ CRITICAL: Cumulative vs. Last Call Usage**

For multi-call systems (like COBBIE, TestAndImprove), use `collector.usage` for **cumulative total** across ALL calls:
```python
from baml_client import b
from baml_py import Collector

def multi_call_function_with_metrics():
    collector = Collector(name="multi-call-collector")

    # Multiple BAML calls with same collector
    result1 = b.FirstCall("input1", baml_options={"collector": collector})
    result2 = b.SecondCall("input2", baml_options={"collector": collector})
    result3 = b.ThirdCall("input3", baml_options={"collector": collector})

    # ✅ CORRECT: Use collector.usage for cumulative total across ALL calls
    input_tokens = 0
    output_tokens = 0

    if collector and hasattr(collector, 'usage') and collector.usage:
        usage = collector.usage
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0

    total_tokens = input_tokens + output_tokens

    # ❌ WRONG: collector.last.usage only gets the VERY LAST call
    # last_usage = collector.last.usage  # Only captures result3 tokens!

    return result3, {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens
    }
```

**🆕 Advanced Dual-Level Token Monitoring (COBBIE Pattern):**
```python
from baml_client import b
from baml_py import Collector
import mlflow

def sophisticated_multi_call_with_metrics():
    """
    Advanced token tracking with dual-level monitoring and comprehensive error handling.

    Tracks both cumulative totals across all calls AND last call details for debugging.
    """
    collector = Collector(name="sophisticated-multi-call")

    try:
        # Multiple iterative calls
        for iteration in range(max_iterations):
            result = b.IterativeCall(f"input_{iteration}", baml_options={"collector": collector})

            # Process result and potentially continue/exit
            if isinstance(result, FinalResult):
                break

        # 🆕 Enhanced token tracking with error handling
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        last_call_tokens = 0
        calls_count = 0

        if collector:
            try:
                # Get cumulative usage across all calls
                if hasattr(collector, 'usage') and collector.usage:
                    usage = collector.usage
                    input_tokens = usage.input_tokens or 0
                    output_tokens = usage.output_tokens or 0
                    total_tokens = input_tokens + output_tokens

                # 🆕 Also get last call info for comparison/debugging
                if (hasattr(collector, 'last') and collector.last and
                    hasattr(collector.last, 'usage') and collector.last.usage):
                    last_usage = collector.last.usage
                    last_call_tokens = (last_usage.input_tokens or 0) + (last_usage.output_tokens or 0)

                # 🆕 Number of calls made for performance analysis
                calls_count = len(collector.logs) if hasattr(collector, 'logs') else 0

                logger.info(f"Token tracking - Cumulative: {total_tokens}, Last call: {last_call_tokens}, Calls: {calls_count}")

            except Exception as e:
                logger.warning(f"Error extracting token usage from collector: {e}")
                # Fallback to zero values
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0
                calls_count = 0
        else:
            logger.warning("No collector available for token tracking")

        # 🆕 Log comprehensive metrics to MLflow
        mlflow.log_metrics({
            "function_input_tokens": input_tokens,
            "function_output_tokens": output_tokens,
            "function_total_tokens": total_tokens,
            "function_last_call_tokens": last_call_tokens,  # For comparison/debugging
            "function_calls_count": calls_count,
            "execution_time_seconds": execution_time,
            "success": 1 if success else 0,
            "avg_tokens_per_call": total_tokens / max(calls_count, 1),
            "efficiency_ratio": total_tokens / max(execution_time, 0.001)  # tokens per second
        })

        # 🆕 Set span attributes for detailed tracing
        if hasattr(mlflow, 'active_run') and mlflow.active_run():
            with mlflow.start_span(name="token_metrics", span_type="ATTRIBUTE") as span:
                span.set_attributes({
                    "token_usage.total": total_tokens,
                    "token_usage.per_call": total_tokens / max(calls_count, 1),
                    "token_usage.last_call": last_call_tokens,
                    "call_count": calls_count,
                    "efficiency.tokens_per_second": total_tokens / max(execution_time, 0.001),
                    "tracking.completeness": "full" if total_tokens > 0 else "partial"
                })

        return final_result, collector

    except Exception as e:
        logger.error(f"Multi-call function failed: {e}")
        raise
```

**Single Call Functions:**
```python
from baml_client import b
from baml_py import Collector

def single_call_function_with_metrics():
    collector = Collector(name="single-call-collector")
    
    result = b.SingleCall("input", baml_options={"collector": collector})

    # For single calls, both approaches work (cumulative == last call)
    usage = collector.usage  # ✅ Preferred: Always use this
    # OR
    usage = collector.last.usage  # ✅ Also works for single calls
    
    return result, {
        "input_tokens": usage.input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0,
        "total_tokens": (usage.input_tokens or 0) + (usage.output_tokens or 0)
    }
```

**Advanced Multi-Call with Error Handling:**
```python
from baml_client import b
from baml_py import Collector

def robust_multi_call_with_metrics():
    collector = Collector(name="robust-collector")
    
    try:
        # Multiple calls that may have different token usage
        result1 = b.IterativeCall("input1", baml_options={"collector": collector})
        result2 = b.IterativeCall("input2", baml_options={"collector": collector})
        
        # Enhanced token tracking with error handling
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        last_call_tokens = 0
        
        if collector:
            try:
                # Get cumulative usage across all calls
                if hasattr(collector, 'usage') and collector.usage:
                    usage = collector.usage
                    input_tokens = usage.input_tokens or 0
                    output_tokens = usage.output_tokens or 0
                    total_tokens = input_tokens + output_tokens
                
                # Also get last call info for comparison/debugging
                if (hasattr(collector, 'last') and collector.last and 
                    hasattr(collector.last, 'usage') and collector.last.usage):
                    last_usage = collector.last.usage
                    last_call_tokens = (last_usage.input_tokens or 0) + (last_usage.output_tokens or 0)
                
                logger.info(f"Token tracking - Cumulative: {total_tokens}, Last call: {last_call_tokens}")
                
            except Exception as e:
                logger.warning(f"Error extracting token usage from collector: {e}")
                # Fallback to zero values
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0
        else:
            logger.warning("No collector available for token tracking")
        
        # Log to MLflow with comprehensive metrics
        mlflow.log_metrics({
            "function_input_tokens": input_tokens,
            "function_output_tokens": output_tokens,
            "function_total_tokens": total_tokens,
            "function_last_call_tokens": last_call_tokens,
            "function_calls_count": len(collector.logs) if collector and hasattr(collector, 'logs') else 0
        })
        
        return result2, collector
        
    except Exception as e:
        logger.error(f"Multi-call function failed: {e}")
        raise
```

### LM_Metrics Integration

**Using Project LM_Metrics Class:**
```python
from src.engine.schemas.outputs import LM_Metrics

def create_lm_metrics_from_collector(collector) -> LM_Metrics:
    # ✅ Use cumulative usage for multi-call systems
    usage = None
    if collector and hasattr(collector, 'usage') and collector.usage:
        usage = collector.usage

    return LM_Metrics(
        input_tokens=usage.input_tokens if usage else 0,
        output_tokens=usage.output_tokens if usage else 0,
        llm="zai-glm-4.6",  # Extract from config or collector
        cost=None  # Calculate if cost rates available
    )
```

**MLflow Integration Pattern:**
```python
def log_comprehensive_metrics(collector, execution_time, success=True):
    """
    Log comprehensive token metrics to MLflow for multi-call systems.
    
    Args:
        collector: BAML Collector with token usage data
        execution_time: Function execution time in seconds
        success: Whether the operation succeeded
    """
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    last_call_tokens = 0
    calls_count = 0
    
    if collector:
        try:
            # Cumulative usage across all calls
            if hasattr(collector, 'usage') and collector.usage:
                usage = collector.usage
                input_tokens = usage.input_tokens or 0
                output_tokens = usage.output_tokens or 0
                total_tokens = input_tokens + output_tokens
            
            # Last call usage for comparison
            if (hasattr(collector, 'last') and collector.last and 
                hasattr(collector.last, 'usage') and collector.last.usage):
                last_usage = collector.last.usage
                last_call_tokens = (last_usage.input_tokens or 0) + (last_usage.output_tokens or 0)
            
            # Number of calls made
            calls_count = len(collector.logs) if hasattr(collector, 'logs') else 0
            
        except Exception as e:
            logger.warning(f"Error extracting metrics from collector: {e}")
    
    # Log comprehensive metrics
    mlflow.log_metrics({
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "last_call_tokens": last_call_tokens,
        "calls_count": calls_count,
        "execution_time_seconds": execution_time,
        "success": 1 if success else 0,
        "avg_tokens_per_call": total_tokens / max(calls_count, 1)
    })
    
    # Set span attributes for detailed tracing
    if hasattr(mlflow, 'active_run') and mlflow.active_run():
        with mlflow.start_span(name="token_metrics", span_type="ATTRIBUTE") as span:
            span.set_attributes({
                "token_usage.total": total_tokens,
                "token_usage.per_call": total_tokens / max(calls_count, 1),
                "call_count": calls_count,
                "efficiency_ratio": total_tokens / max(execution_time, 0.001)  # tokens per second
            })
```

## 🆕 Advanced Iteration Management Patterns

### Per-Iteration Span Management

**COBBIE-Style Iteration Tracking:**
```python
def advanced_iteration_management():
    """
    Sophisticated iteration management with comprehensive tracking.

    Each iteration gets its own span with detailed metrics and status management.
    """
    # Initialize state tracking
    previous_attempts = ""
    code_execution_count = 0
    total_code_execution_time = 0
    llm_calls = 0

    # Main reasoning loop with per-iteration spans
    for iteration in range(max_iterations):
        iteration_start = time.time()

        # Create dedicated span for this iteration
        with mlflow.start_span(
            name=f"Iteration_{iteration + 1}", span_type="CHAIN"
        ) as iteration_span:

            # Extract token usage for this specific iteration
            iteration_input_tokens = 0
            iteration_output_tokens = 0
            iteration_total_tokens = 0

            # LLM call span within iteration
            with mlflow.start_span(
                name=f"LLM_call_{iteration + 1}", span_type="LLM"
            ) as llm_span:
                llm_span.set_inputs({
                    "question": question,
                    "available_tools": tools_docs,
                    "previous_attempts": previous_attempts,
                    "iteration": iteration + 1,
                })

                # BAML function call
                result = _code_act_iter(
                    user_input=question,
                    available_tools=tools_docs,
                    previous_attempts=previous_attempts,
                    **kwargs
                )

                # Calculate iteration duration
                iteration_duration = time.time() - iteration_start
                llm_calls += 1

                # Extract token usage for this iteration
                if collector and collector.last and collector.last.usage:
                    usage = collector.last.usage
                    iteration_input_tokens = usage.input_tokens or 0
                    iteration_output_tokens = usage.output_tokens or 0
                    iteration_total_tokens = iteration_input_tokens + iteration_output_tokens

                # Log LLM call metrics
                llm_span.set_attributes({
                    "llm.provider": llm_provider,
                    "llm.model": llm_name,
                    "input_tokens": iteration_input_tokens,
                    "output_tokens": iteration_output_tokens,
                    "total_tokens": iteration_total_tokens,
                    "latency": iteration_duration,
                })

                llm_span.set_outputs({
                    "result_type": type(result).__name__,
                    "iteration": iteration + 1,
                })

            # Handle union type flow control with iteration-level tracking
            if isinstance(result, FinalAnswer):
                # Success case - update iteration span with final results
                iteration_span.set_outputs({
                    "final_answer": result.answer,
                    "final_reasoning": result.thoughts,
                    "total_iterations": iteration + 1,
                    "llm_calls": llm_calls,
                    "code_executions": code_execution_count,
                    "iteration_success": True,
                    "final_iteration_input_tokens": iteration_input_tokens,
                    "final_iteration_output_tokens": iteration_output_tokens,
                    "final_iteration_total_tokens": iteration_total_tokens,
                })

                iteration_span.set_attributes({
                    "token_usage.final_iteration_input": iteration_input_tokens,
                    "token_usage.final_iteration_output": iteration_output_tokens,
                    "token_usage.final_iteration_total": iteration_total_tokens,
                })

                iteration_span.set_status("OK")
                return result

            elif isinstance(result, CodeAction):
                # Continue iteration - execute code and update state
                current_attempt = _execute_code_action(
                    code_action=result,
                    iteration=iteration,
                    tools=tools,
                    model_path=model_path,
                )

                # Update state for next iteration
                previous_attempts += f"\n{current_attempt}\n"
                code_execution_count += 1

                # Set iteration span with progress information
                iteration_span.set_attributes({
                    "token_usage.input_tokens": iteration_input_tokens,
                    "token_usage.output_tokens": iteration_output_tokens,
                    "token_usage.total_tokens": iteration_total_tokens,
                    "code_execution_count": code_execution_count,
                })

                iteration_span.set_status("OK")
                continue

            else:
                # Handle unexpected result type
                error_msg = f"Unexpected result type: {type(result)}"
                logger.error(error_msg)

                previous_attempts += (
                    f"\n--- Iteration {iteration + 1} ---\nError:\n{error_msg}"
                )

                iteration_span.set_outputs({
                    "error_msg": error_msg,
                })

                iteration_span.set_attributes({
                    "token_usage.input_tokens": iteration_input_tokens,
                    "token_usage.output_tokens": iteration_output_tokens,
                    "token_usage.total_tokens": iteration_total_tokens,
                })

                iteration_span.set_status("ERROR")
                continue

    # Max iterations reached - create comprehensive final span
    with mlflow.start_span(
        name="Max_Iterations_Reached", span_type="CHAIN"
    ) as final_span:
        final_span.set_inputs({
            "max_iterations": max_iterations,
            "total_iterations_completed": max_iterations,
            "llm_calls": llm_calls,
            "code_executions": code_execution_count,
            "total_code_execution_time": total_code_execution_time,
        })

        # Create comprehensive final answer with partial results
        final_answer = FinalAnswer(
            thoughts=(
                f"Reached maximum iteration limit ({max_iterations}) without resolving the question. "
                f"Summary:\n"
                f"- Total iterations: {max_iterations}\n"
                f"- LLM calls: {llm_calls}\n"
                f"- Code executions: {code_execution_count}\n"
                f"- Total code execution time: {total_code_execution_time:.2f}s\n\n"
                f"Last 3 attempts:\n" + "\n".join(previous_attempts[-3:])
                if previous_attempts
                else "No previous attempts"
            ),
            answer=(
                "Unable to complete the request due to iteration limit. "
                "The question may be too complex or required information may not be accessible "
                "with the available tools."
            ),
        )

        final_span.set_outputs({
            "answer": final_answer.answer,
            "reasoning": final_answer.thoughts,
            "termination_reason": "max_iterations_reached",
            "summary": {
                "max_iterations": max_iterations,
                "llm_calls": llm_calls,
                "code_executions": code_execution_count,
                "total_code_execution_time": total_code_execution_time,
                "partial_results_count": len(previous_attempts),
            },
        })

        final_span.set_status("OK")
        return final_answer
```

### State Management Across Iterations

**Previous Attempts Accumulation Pattern:**
```python
def manage_iteration_state():
    """
    Effective state management across multiple iterations.

    Maintains comprehensive history while avoiding memory bloat.
    """
    previous_attempts = ""

    for iteration in range(max_iterations):
        # Generate current attempt
        current_attempt = generate_attempt_result(
            iteration=iteration,
            question=question,
            previous_context=previous_attempts
        )

        # 🆕 Smart state updates with formatting
        if iteration == 0:
            previous_attempts = f"--- Iteration 1 ---\n{current_attempt}"
        else:
            previous_attempts += f"\n--- Iteration {iteration + 1} ---\n{current_attempt}"

        # 🆕 Optional: Limit history size to prevent memory issues
        if len(previous_attempts) > 10000:  # 10k character limit
            # Keep only recent iterations
            lines = previous_attempts.split('\n')
            recent_lines = lines[-20:]  # Keep last 20 lines
            previous_attempts = '\n'.join(recent_lines)

        # Continue with next iteration using updated state
        result = process_next_iteration(previous_attempts)
```

## 🆕 Advanced Patterns for Complex Systems

### Comprehensive Span Architecture

**Production-Quality Span Hierarchy (COBBIE Reference):**
```python
def production_span_architecture():
    """
    Comprehensive span architecture for complex multi-iteration systems.

    This pattern demonstrates proper span hierarchy, attribute naming,
    and status management for production environments.
    """
    # Check if we're already in an MLflow run
    active_run = mlflow.active_run()
    run_context_manager = (
        nullcontext()
        if active_run
        else mlflow.start_run(run_name="ComplexSystem_Execution_Run")
    )

    with run_context_manager:
        # Log comprehensive parameters following run_evaluation.py pattern
        mlflow.log_params({
            "component": "ComplexSystem",
            "engine_type": "baml",
            "max_iterations": max_iterations,
            "tools_count": len(tools),
            "llm_provider": llm_provider,
            "llm_model": llm_name,
            "tools": ", ".join(tools.keys()),
            "session_id": session_id,
            "user_id": user_id,
        })

        # Main execution span with comprehensive tracking
        with mlflow.start_span(name="ComplexSystem", span_type="CHAIN") as main_span:
            start_time = time.time()

            # Set comprehensive span inputs
            main_span.set_inputs({
                "user_input": user_input,
                "max_iterations": max_iterations,
                "tools_count": len(tools),
                "session_id": session_id,
            })

            # Set span attributes for categorization and filtering
            main_span.set_attributes({
                "component.name": "ComplexSystem",
                "component.version": "2.0.0",
                "component.type": "iterative_reasoning",
                "execution.mode": "production",
                "llm.provider": llm_provider,
                "llm.model": llm_name,
                "feature.multi_iteration": True,
                "feature.code_execution": True,
                "feature.error_handling": "advanced",
            })

            # Initialize comprehensive metrics
            total_iterations = 0
            successful_iterations = 0
            failed_iterations = 0
            total_llm_calls = 0
            total_code_executions = 0
            total_tokens = 0
            critical_errors = []

            # Multi-iteration processing with detailed tracking
            for iteration in range(max_iterations):
                total_iterations += 1

                with mlflow.start_span(
                    name=f"Iteration_{iteration + 1}", span_type="CHAIN"
                ) as iteration_span:

                    iteration_start = time.time()

                    # Set iteration attributes
                    iteration_span.set_attributes({
                        "iteration.number": iteration + 1,
                        "iteration.total": max_iterations,
                        "iteration.progress": (iteration + 1) / max_iterations,
                    })

                    try:
                        # LLM call span with comprehensive tracking
                        with mlflow.start_span(
                            name=f"LLM_Call_{iteration + 1}", span_type="LLM"
                        ) as llm_span:
                            llm_span.set_inputs({
                                "question": question,
                                "iteration": iteration + 1,
                                "context_length": len(previous_attempts),
                            })

                            # BAML function call
                            result, collector = run_baml_function_with_metrics(
                                component_name=f"Iteration_{iteration + 1}",
                                baml_function=b.ProcessInput,
                                question=question,
                                context=previous_attempts,
                                **kwargs
                            )

                            total_llm_calls += 1
                            iteration_duration = time.time() - iteration_start

                            # Extract token usage with error handling
                            iteration_tokens = 0
                            if collector and hasattr(collector, 'last') and collector.last:
                                if hasattr(collector.last, 'usage') and collector.last.usage:
                                    usage = collector.last.usage
                                    iteration_tokens = (usage.input_tokens or 0) + (usage.output_tokens or 0)
                                    total_tokens += iteration_tokens

                            # Set LLM span attributes
                            llm_span.set_attributes({
                                "llm.provider": llm_provider,
                                "llm.model": llm_name,
                                "tokens.input": collector.last.usage.input_tokens if collector.last and hasattr(collector.last, 'usage') else 0,
                                "tokens.output": collector.last.usage.output_tokens if collector.last and hasattr(collector.last, 'usage') else 0,
                                "tokens.total": iteration_tokens,
                                "latency.ms": iteration_duration * 1000,
                                "iteration": iteration + 1,
                            })

                            llm_span.set_outputs({
                                "result_type": type(result).__name__,
                                "has_code_action": isinstance(result, CodeAction),
                                "has_final_answer": isinstance(result, FinalAnswer),
                            })

                        # Process result with comprehensive tracking
                        if isinstance(result, FinalAnswer):
                            successful_iterations += 1

                            # Set successful iteration span
                            iteration_span.set_outputs({
                                "result_type": "final_answer",
                                "final_answer": result.answer,
                                "final_reasoning": result.thoughts,
                                "iteration_success": True,
                                "total_iterations": iteration + 1,
                                "tokens_used": iteration_tokens,
                                "duration": iteration_duration,
                            })

                            iteration_span.set_attributes({
                                "status.success": True,
                                "status.completion": "success",
                                "tokens.iteration": iteration_tokens,
                            })

                            iteration_span.set_status("OK")

                            # Update main span with final results
                            main_span.set_outputs({
                                "answer": result.answer,
                                "reasoning": result.thoughts,
                                "total_iterations": total_iterations,
                                "successful_iterations": successful_iterations,
                                "failed_iterations": failed_iterations,
                                "total_llm_calls": total_llm_calls,
                                "total_tokens": total_tokens,
                                "execution_time": time.time() - start_time,
                                "success": True,
                                "completion_reason": "successful_completion",
                            })

                            main_span.set_attributes({
                                "execution.success": True,
                                "completion.reason": "successful_completion",
                                "performance.tokens_per_second": total_tokens / max(time.time() - start_time, 0.001),
                                "efficiency.iterations_needed": total_iterations,
                            })

                            main_span.set_status("OK")

                            # Log final metrics to MLflow
                            mlflow.log_metrics({
                                "complex_system_total_iterations": total_iterations,
                                "complex_system_successful_iterations": successful_iterations,
                                "complex_system_total_tokens": total_tokens,
                                "complex_system_execution_time": time.time() - start_time,
                                "complex_system_success": 1,
                            })

                            return result, create_comprehensive_metrics(
                                total_iterations=total_iterations,
                                total_tokens=total_tokens,
                                execution_time=time.time() - start_time,
                                collector=collector
                            )

                        elif isinstance(result, CodeAction):
                            # Execute code and continue
                            code_result = execute_code_code_action(result)
                            total_code_executions += 1

                            # Update state for next iteration
                            previous_attempts += f"\n{code_result}\n"

                            iteration_span.set_outputs({
                                "result_type": "code_action",
                                "code_executed": True,
                                "execution_result": code_result,
                                "iteration_success": True,
                                "tokens_used": iteration_tokens,
                                "duration": iteration_duration,
                            })

                            iteration_span.set_attributes({
                                "status.success": True,
                                "status.completion": "continue",
                                "tokens.iteration": iteration_tokens,
                                "code.executed": True,
                            })

                            iteration_span.set_status("OK")
                            successful_iterations += 1
                            continue

                        else:
                            # Handle unexpected result type
                            failed_iterations += 1
                            error_msg = f"Unexpected result type: {type(result)}"

                            iteration_span.set_outputs({
                                "result_type": "error",
                                "error_message": error_msg,
                                "iteration_success": False,
                                "tokens_used": iteration_tokens,
                                "duration": iteration_duration,
                            })

                            iteration_span.set_attributes({
                                "status.success": False,
                                "status.completion": "error",
                                "error.type": "unexpected_result_type",
                                "tokens.iteration": iteration_tokens,
                            })

                            iteration_span.set_status("ERROR")
                            continue

                    except Exception as e:
                        failed_iterations += 1
                        error_msg = f"Iteration {iteration + 1} failed: {str(e)}"

                        # Check if critical error
                        is_critical = any(keyword in error_msg.lower() for keyword in ["permission", "auth", "api key"])
                        if is_critical:
                            critical_errors.append({"iteration": iteration + 1, "error": error_msg})

                        iteration_span.set_outputs({
                            "result_type": "exception",
                            "error_message": error_msg,
                            "error_type": type(e).__name__,
                            "is_critical": is_critical,
                            "iteration_success": False,
                            "duration": time.time() - iteration_start,
                        })

                        iteration_span.set_attributes({
                            "status.success": False,
                            "status.completion": "exception",
                            "error.type": type(e).__name__,
                            "error.critical": is_critical,
                        })

                        iteration_span.set_status("ERROR")

                        if is_critical:
                            logger.error(f"Critical error in iteration {iteration + 1}: {e}")
                            break
                        else:
                            logger.warning(f"Non-critical error in iteration {iteration + 1}: {e}")
                            continue

            # Max iterations reached - create comprehensive final result
            main_span.set_outputs({
                "answer": "Maximum iterations reached without completion",
                "reasoning": f"Process stopped after {max_iterations} iterations",
                "total_iterations": total_iterations,
                "successful_iterations": successful_iterations,
                "failed_iterations": failed_iterations,
                "total_llm_calls": total_llm_calls,
                "total_code_executions": total_code_executions,
                "total_tokens": total_tokens,
                "execution_time": time.time() - start_time,
                "success": False,
                "completion_reason": "max_iterations_reached",
                "critical_errors": len(critical_errors),
            })

            main_span.set_attributes({
                "execution.success": False,
                "completion.reason": "max_iterations_reached",
                "performance.tokens_per_second": total_tokens / max(time.time() - start_time, 0.001),
                "efficiency.success_rate": successful_iterations / max(total_iterations, 1),
            })

            main_span.set_status("OK")

            # Log final metrics
            mlflow.log_metrics({
                "complex_system_total_iterations": total_iterations,
                "complex_system_successful_iterations": successful_iterations,
                "complex_system_failed_iterations": failed_iterations,
                "complex_system_total_tokens": total_tokens,
                "complex_system_execution_time": time.time() - start_time,
                "complex_system_success": 0,
                "complex_system_critical_errors": len(critical_errors),
            })

            # Create comprehensive incomplete result
            final_result = create_incomplete_result(
                total_iterations=total_iterations,
                successful_iterations=successful_iterations,
                failed_iterations=failed_iterations,
                critical_errors=critical_errors,
                previous_attempts=previous_attempts
            )

            return final_result, create_comprehensive_metrics(
                total_iterations=total_iterations,
                total_tokens=total_tokens,
                execution_time=time.time() - start_time,
                success=False,
                collector=collector
            )
```

### Attribute Naming Standards

**🆕 Standardized Attribute Naming Convention:**
```python
def set_standardized_attributes(span, **kwargs):
    """
    Set standardized attributes for consistent filtering and analysis.

    Follows dot-notation hierarchy for logical grouping.
    """
    # Standard naming patterns:
    # - component.*: Component identification
    # - execution.*: Execution metadata
    # - performance.*: Performance metrics
    # - token.*: Token usage information
    # - error.*: Error-related information
    # - status.*: Status information
    # - iteration.*: Iteration-specific data

    standard_attributes = {
        # Component identification
        "component.name": kwargs.get("component_name", "Unknown"),
        "component.version": kwargs.get("component_version", "1.0.0"),
        "component.type": kwargs.get("component_type", "function"),

        # Execution metadata
        "execution.mode": kwargs.get("execution_mode", "production"),
        "execution.environment": kwargs.get("environment", "development"),
        "execution.session_id": kwargs.get("session_id", ""),
        "execution.user_id": kwargs.get("user_id", ""),

        # Performance metrics
        "performance.tokens_per_second": kwargs.get("tokens_per_second", 0),
        "performance.iterations_per_second": kwargs.get("iterations_per_second", 0),
        "performance.efficiency_score": kwargs.get("efficiency_score", 0),

        # Token usage
        "token.input": kwargs.get("input_tokens", 0),
        "token.output": kwargs.get("output_tokens", 0),
        "token.total": kwargs.get("total_tokens", 0),
        "token.calls_count": kwargs.get("calls_count", 0),

        # Status information
        "status.success": kwargs.get("success", False),
        "status.completion": kwargs.get("completion_reason", "unknown"),
        "status.error_type": kwargs.get("error_type", ""),
    }

    # Set only non-zero/non-empty attributes to reduce noise
    for key, value in standard_attributes.items():
        if value not in [0, "", None, False]:
            span.set_attribute(key, value)

    # Set custom attributes
    for key, value in kwargs.items():
        if key not in standard_attributes:
            span.set_attribute(f"custom.{key}", value)
```

## Essential Code Patterns

### Function Signature Patterns

**Simple Function:**
```python
def simple_function(
    required_param: str,
    optional_param: Optional[str] = None
) -> ReturnType:
    """Simple function without MLflow orchestration."""
    result, _ = run_baml_function_with_metrics(
        component_name="SimpleFunction",
        baml_function=b.BamlFunction,
        required_param=required_param,
        optional_param=optional_param
    )
    return result
```

**Function with Metrics:**
```python
def function_with_metrics(
    required_param: str,
    optional_param: Optional[str] = None,
    mlflow: bool = True
) -> Tuple[ReturnType, LM_Metrics]:
    """Function with metrics and optional MLflow orchestration."""
    # Implementation as shown in previous sections
```

### Integration with Orchestration Code

**Direct Function Usage:**
```python
# In evaluation script or orchestration code
from src.engine.components.baml_answer_verifier import verify_answer_with_metrics

def process_question(question, category, ground_truth, answer):
    if answer and ground_truth:
        result, metrics = verify_answer_with_metrics(
            question=question,
            category=category,
            ground_truth=ground_truth,
            system_response=answer
        )

        # Update aggregate metrics
        total_input_tokens += metrics.input_tokens
        total_output_tokens += metrics.output_tokens

        return result.classification
    return None
```

### Union Type Flow Control

**BAML Union Type Pattern:**
```python
def process_baml_result(result):
    """Handle union types from BAML functions."""
    if isinstance(result, SuccessfulResult):
        # Handle success case
        return process_success(result)
    elif isinstance(result, CodeAction):
        # Handle code execution case
        execution_result = execute_code(result.python_code)
        return process_execution(execution_result)
    elif isinstance(result, AssessmentResult):
        # Handle assessment case
        return process_assessment(result)
    else:
        # Handle unexpected types
        logger.warning(f"Unexpected result type: {type(result)}")
        return default_handler(result)
```

## Migration Checklist

### Pre-Migration Preparation

- [ ] **Analyze Current OOP Structure**: Identify `__init__`, `forward` method, and dependencies
- [ ] **Review Configuration Usage**: Understand how config and LM are accessed
- [ ] **Document Current MLflow Integration**: Note existing spans and logging patterns
- [ ] **Identify Test Cases**: Ensure comprehensive test coverage for current functionality

### Migration Steps

1. **Create BAML Schema** (if not exists):
   ```bash
   # Convert DSPy signatures to BAML schemas
   uv run baml-cli generate
   ```

2. **Implement Two-Function Pattern** (REQUIRED):
   - [ ] **Base Function**: `function_name()` returning only result type
   - [ ] **Metrics Function**: `function_name_with_metrics()` with `mlflow: bool = True` parameter
   - [ ] **MLflow Parameter**: Always include `mlflow: bool = True` in metrics function
   - [ ] **Return Type**: Metrics function must return `Tuple[ResultType, LM_Metrics]`
   - [ ] Use `run_baml_function_with_metrics()` wrapper in both functions
   - [ ] Add MLflow orchestration spans only in metrics function
   - [ ] Implement proper error handling with span status management

3. **Update Integration Points**:
   - [ ] Update orchestration code to use `_with_metrics` function variant
   - [ ] Remove class instantiation and `.forward()` calls
   - [ ] Update token tracking to use `LM_Metrics` from collectors
   - [ ] Verify MLflow spans are created correctly

4. **Testing and Validation**:
   - [ ] Run existing test suite against functional version
   - [ ] Verify MLflow spans and token tracking work correctly
   - [ ] Compare outputs between OOP and functional versions
   - [ ] Performance testing (should be improved)

### Common Pitfalls to Avoid

#### MLflow Context Issues
- **Problem**: Spans created outside MLflow run context cause warnings
- **Solution**: Check for active run before creating spans, use `nullcontext()` fallback
- **Pattern**: 
  ```python
  active_run = mlflow.active_run()
  run_context_manager = nullcontext() if active_run else mlflow.start_run(run_name="Component_Execution_Run")
  ```

#### Token Usage Variables
- **Problem**: Using `collector.last.usage` for multi-call systems, missing cumulative totals
- **Solution**: Use `collector.usage` for cumulative totals, `collector.last.usage` only for single calls
- **Pattern**:
  ```python
  # ✅ CORRECT: Multi-call systems (COBBIE, TestAndImprove, etc.)
  if collector and hasattr(collector, 'usage') and collector.usage:
      usage = collector.usage
      input_tokens = usage.input_tokens or 0
      output_tokens = usage.output_tokens or 0
  total_tokens = input_tokens + output_tokens
  
  # ❌ WRONG: collector.last.usage only gets the VERY LAST call
  # This causes major underreporting for iterative systems
  if collector and collector.last and collector.last.usage:
      usage = collector.last.usage  # Only captures final iteration!
  ```

#### Cumulative Token Tracking Pitfall
- **Problem**: Critical error in token monitoring for multi-call systems (COBBIE, TestAndImprove)
- **Impact**: Massive underreporting of token usage (up to 90%+ underreporting for 10+ iterations)
- **Root Cause**: Using `collector.last.usage` instead of `collector.usage` 
- **When It Happens**: Any BAML function that makes multiple LLM calls across iterations
- **Detection**: MLflow shows unexpectedly low token counts for complex operations
- **Fix Pattern**:
  ```python
  # ❌ WRONG - Only captures final iteration
  if collector and collector.last and collector.last.usage:
      usage = collector.last.usage  # ~50 tokens for final iteration only
      input_tokens = usage.input_tokens or 0
      output_tokens = usage.output_tokens or 0
  
  # ✅ CORRECT - Captures ALL iterations
  if collector and hasattr(collector, 'usage') and collector.usage:
      usage = collector.usage  # ~500+ tokens for 10 iterations
      input_tokens = usage.input_tokens or 0  
      output_tokens = usage.output_tokens or 0
  ```
- **Real-World Impact**: COBBIE function was reporting ~50 tokens instead of ~500+ tokens for 10-iteration runs

#### Parameter Logging
- **Problem**: Missing experiment parameters for reproducibility
- **Solution**: Log comprehensive parameters following `run_evaluation.py` pattern
- **Pattern**:
  ```python
  params = {
      "component": "COMPONENT_NAME",
      "engine_type": "baml",
      "max_iterations": max_iterations,
      "tools_count": len(tools),
      "llm_provider": "Z.AI",
      "llm_model": "GLM-4.6"
  }
  mlflow.log_params(params)
  ```

- **Incorrect MLflow Context Usage**: Always use context managers, never create spans directly
- **Missing Collector Usage**: Don't forget to extract token usage from collectors
- **Incomplete Error Handling**: Ensure spans are properly closed with error status
- **Configuration Access**: Use environment variables or imported configs, not instance variables
- **Type Safety**: Maintain proper type hints and union type handling

### Testing Strategies

**Unit Testing:**
```python
def test_functional_version():
    result = verify_answer(
        question="Test question",
        category=1,
        ground_truth="Expected answer",
        system_response="Actual answer"
    )
    assert result.classification in ["correct", "wrong", "abstained"]

def test_function_with_metrics():
    result, metrics = verify_answer_with_metrics(
        question="Test question",
        category=1,
        ground_truth="Expected answer",
        system_response="Actual answer",
        mlflow=False  # Disable MLflow for unit tests
    )
    assert metrics.input_tokens >= 0
    assert metrics.output_tokens >= 0
```

**Integration Testing:**
```python
def test_mlflow_integration():
    with mlflow.start_run() as run:
        result, metrics = verify_answer_with_metrics(
            question="Test question",
            category=1,
            ground_truth="Expected answer",
            system_response="Actual answer",
            mlflow=True
        )

        # Verify MLflow spans were created
        # Check span inputs/outputs contain expected data
```

**COBBIE Integration Example:**
```python
def test_cobbie_with_metrics():
    tools = create_demo_tools()
    question = "How many walls in the building?"
    
    final_answer, collector = cobbie_with_metrics(
        user_input=question,
        tools=tools,
        max_iterations=5
    )
    
    assert final_answer.answer is not None
    assert collector.last.usage.input_tokens > 0
    assert collector.last.usage.output_tokens > 0
```

## Conclusion

This functional BAML approach provides:

### Core Benefits
- **Better Observability**: Comprehensive MLflow integration with nested span hierarchies
- **Cleaner Code**: Pure functions instead of complex class hierarchies
- **Improved Performance**: Direct token tracking and reduced overhead
- **Enhanced Maintainability**: Easier testing and reasoning

### 🆕 Advanced Capabilities (COBBIE-style)
- **Production-Quality Observability**: 3-level span hierarchy with comprehensive attribute tracking
- **Sophisticated Token Monitoring**: Dual-level tracking (cumulative + per-iteration) with call counting
- **Robust Error Handling**: Per-iteration error classification with severity-based flow control
- **Advanced Iteration Management**: State management with smart history accumulation
- **Context-Aware Integration**: Graceful handling of existing MLflow runs with `nullcontext()` pattern

### Reference Implementations

**🆕 Production Reference**: The COBBIE implementation in `src/engine/components/cobbie.py` serves as the canonical reference for advanced patterns, demonstrating:
- Real-world production quality
- Comprehensive MLflow integration
- Sophisticated error handling and state management
- Advanced token tracking and performance monitoring

**Simple Component Reference**: The AnswerVerifier implementation in `src/engine/components/baml_answer_verifier.py` provides basic 2-function pattern guidance for simpler components.

### Migration Philosophy

The updated guide reflects a progression from theoretical patterns to production-proven implementations, ensuring developers have access to:
- **Real-world patterns** from actual production code
- **Scalable architectures** that handle complex multi-iteration systems
- **Comprehensive observability** suitable for enterprise environments
- **Robust error handling** that maintains system stability under failure conditions

This approach ensures that migrated components not only work correctly but also meet the operational requirements of production systems.
