# BAML Functional Migration Guide

This guide provides patterns and best practices for converting OOP DSPy agents to functional BAML approach, with integrated MLflow tracing and metrics tracking.

## 🎯 Quick Reference: Required Patterns

**Every migrated agent MUST follow this pattern:**

1. **Two Functions**: Always create both `function_name()` and `function_name_with_metrics()`
2. **MLflow Parameter**: The `_with_metrics` function always has `mlflow: bool = True`
3. **Return Types**: Base function returns `ResultType`, metrics function returns `Tuple[ResultType, LM_Metrics]`
4. **Configuration**: Most config goes in `.baml` files, with runtime overrides via `ClientRegistry`
5. **⚠️ Token Tracking**: Use `collector.usage` for cumulative totals, `collector.last.usage` only for single calls

**Example Template:**
```python
def my_function(param1: str, param2: Optional[str] = None) -> ResultType:
    """Base function - no MLflow orchestration."""
    # Implementation using run_baml_function_with_metrics()
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
    
    # Implementation with MLflow spans and LM_Metrics return
    pass
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

See `src/engine/components/baml_answer_verifier.py` for the complete example of this migration pattern.

## Pattern Conversion: Class → Function

### Standard Function Pattern (REQUIRED)

**Every agent MUST follow this two-function pattern:**

1. **Base Function**: Simple function returning just the result
2. **Function with Metrics**: Returns tuple of `(result, LM_Metrics)` with MLflow support

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

**BAML Functional Pattern (REQUIRED):**
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
    # Implementation with MLflow spans and metrics collection
    # (See MLflow Integration Patterns section for full implementation)
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

**Standard Span Pattern:**
```python
import mlflow

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

**Comprehensive Error Handling:**
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
- **Better Observability**: Comprehensive MLflow integration
- **Cleaner Code**: Pure functions instead of complex class hierarchies
- **Improved Performance**: Direct token tracking and reduced overhead
- **Enhanced Maintainability**: Easier testing and reasoning

The AnswerVerifier implementation in `src/engine/components/baml_answer_verifier.py` serves as the canonical reference for these patterns.
