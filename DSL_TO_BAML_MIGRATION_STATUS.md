# DSPy to BAML Migration Status & Guidelines

## 🎯 Migration Overview

Successfully migrated **ToolCreator** component from DSPy to BAML with enhanced MLflow tracing and simplified architecture. The migration demonstrates significant improvements in performance, clarity, and observability.

## ✅ Completed Components

### 1. ToolCreator (✅ COMPLETE)
- **Status**: Fully migrated and tested
- **Files**:
  - `baml_src/tool_creator.baml` - BAML schema
  - `src/engine/components/tool_creator_baml.py` - BAML implementation
  - `src/engine/util/baml_common.py` - Reusable utilities
- **Performance**: 1 iteration vs multiple DSPy iterations
- **Validation**: Successfully integrates with existing TestAndImprove pipeline

## 🏗️ Architecture Rules & Patterns

### 1. ✅ Eliminate ModuleOutput
- **Rule**: Use BAML's strong typing and union types directly
- **Pattern**: `CodeAction | FunctionImplementation` instead of complex state management
- **Benefits**: Cleaner flow control, type safety, reduced complexity

### 2. ✅ Enhanced MLflow Tracing
- **Rule**: Comprehensive logging with actual parameters, not generic metadata
- **Input Logging**: Real function parameters (function_requirements, function_name, path_ifc_model, etc.)
- **Output Logging**: Actual output fields (python_code, thought, function_implementation)
- **LLM Interactions**:
  - System prompt, user prompt, final prompt as span attributes
  - Raw LLM response as artifact
  - Token usage tracking via BAML Collector API

### 3. ✅ Direct Token Monitoring
- **Rule**: Use BAML Collector API for token tracking
- **Pattern**: `collector.last.usage.input_tokens`, `collector.last.usage.output_tokens`
- **No Abstraction**: Direct access without extra wrapper layers

### 4. ✅ Simplified Code Execution Logging
- **Rule**: Minimal logging for code execution spans
- **Input**: Only `python_code`
- **Output**: Only `result` (execution output or error)
- **Removed**: Generic metadata like code_length, line_count, etc.

### 5. ✅ Reusable Component Base
- **Rule**: Extract common patterns into base classes
- **Implementation**: `BamlComponentBase` with shared setup methods
- **Features**: Tool setup, interpreter configuration, documentation generation

## 📁 File Structure

```
baml_src/
├── tool_creator.baml          # ✅ ToolCreator BAML schema
└── schemas.baml               # Existing shared schemas

src/engine/
├── components/
│   ├── tool_creator_baml.py   # ✅ BAML ToolCreator implementation
│   ├── test_and_improve.py    # 🔄 Next migration target
│   ├── tool_assessor.py       # 🔄 Part of TestAndImprove
│   └── tool_corrector.py      # 🔄 Part of TestAndImprove
├── util/
│   └── baml_common.py         # ✅ Reusable BAML utilities
└── schemas.py                 # Existing Pydantic schemas
```

## 🎛️ BAML Patterns Established

### 1. Union Types for Flow Control
```baml
function ToolCreator(...) -> CodeAction | FunctionImplementation
```

### 2. Collector Integration
```python
result, collector = run_baml_function_with_metrics(
    "ToolCreator",
    b.ToolCreator,
    function_requirements=function_requirements,
    function_name=function_name,
    # ... other params
)
```

### 3. Enhanced MLflow Attributes
```python
# Model configuration
span.set_attribute("llm.model", prompt_data["model"])
span.set_attribute("llm.temperature", prompt_data["temperature"])

# Message content
span.set_attribute("llm.system_prompt", system_content)
span.set_attribute("llm.user_prompt", user_content)

# Token usage
mlflow.log_metric("input_tokens", input_tokens)
mlflow.log_metric("output_tokens", output_tokens)
```

## 🚀 Performance Improvements

### ToolCreator Results:
- **DSPy**: Multiple iterations with complex state management
- **BAML**: 1 iteration with clean union types
- **Token Tracking**: Direct access via Collector API
- **MLflow Integration**: Rich, detailed tracing with actual parameters

## 📋 Next Migration: TestAndImprove Component

### Current State:
- **File**: `src/engine/components/test_and_improve.py`
- **Architecture**: DSPy-based with ModuleOutput
- **Dependencies**: ToolAssessor, ToolCorrector (both DSPy)

### Migration Tasks:

#### 1. Create BAML Schema
```baml
// test_and_improve.baml
class AssessmentResult {
    status: string  # "pass" | "fail" | "needs_improvement"
    confidence: float?
    feedback: string
    suggestions: string[]?
}

class ImprovementAction {
    improved_code: string
    reasoning: string
    changes_made: string
}

function TestAndImprove(
    function_implementation: string,
    function_requirements: string,
    function_name: string,
    path_ifc_model: string,
    previous_attempts: string?
) -> AssessmentResult | ImprovementAction
```

#### 2. Create BAML TestAndImprove Component
```python
# src/engine/components/test_and_improve_baml.py
class TestAndImproveBAML(BamlComponentBase):
    def forward(self, function_implementation, function_requirements, function_name, path_ifc_model):
        # Use BAML union types for clean flow control
        result, collector = run_baml_function_with_metrics(
            "TestAndImprove",
            b.TestAndImprove,
            function_implementation=function_implementation,
            function_requirements=function_requirements,
            function_name=function_name,
            path_ifc_model=path_ifc_model
        )

        if isinstance(result, AssessmentResult):
            # Assessment complete
            return ModuleOutput(result=result, status="success")
        elif isinstance(result, ImprovementAction):
            # Execute improved code
            execution_result = self._execute_improvement(result)
            # Continue with assessment
```

#### 3. Migrate ToolAssessor & ToolCorrector
- **ToolAssessor**: BAML function returning AssessmentResult
- **ToolCorrector**: BAML function returning ImprovementAction
- **Integration**: Use same patterns as ToolCreator

#### 4. Update Integration Points
- **ToolCreator**: Update to use TestAndImproveBAML
- **Engine**: Update imports and instantiation
- **Tests**: Update test files

### Benefits of TestAndImprove Migration:
- **Cleaner Flow**: Union types instead of DSPy state management
- **Better Tracing**: MLflow integration with actual parameters
- **Token Tracking**: Direct monitoring via Collector API
- **Consistency**: Same patterns as ToolCreator
- **Performance**: Expected improvements similar to ToolCreator

## 🔧 Implementation Guidelines

### 1. BAML Function Design
- Use union types for clean flow control
- Keep functions focused and single-purpose
- Leverage existing schemas when possible

### 2. MLflow Integration
- Always use `run_baml_function_with_metrics` wrapper
- Log actual parameters, not generic metadata
- Include LLM interaction details as span attributes
- Preserve artifacts for complete reference

### 3. Error Handling
- Use try/catch for BAML function calls
- Log errors with detailed context
- Provide meaningful error messages

### 4. Token Monitoring
- Always track tokens via Collector API
- Log input/output tokens as metrics
- Aggregate token usage across components

## 📈 Success Metrics

### ToolCreator Success:
- ✅ Reduced iterations (1 vs multiple)
- ✅ Enhanced tracing (actual parameters + LLM details)
- ✅ Direct token monitoring
- ✅ Eliminated ModuleOutput complexity
- ✅ Maintained TestAndImprove integration

### Expected TestAndImprove Success:
- Similar iteration reduction
- Enhanced assessment tracing
- Clear improvement action tracking
- Simplified flow control
- Consistent token monitoring

## 🎯 Next Steps

1. **Create TestAndImprove BAML schema** - Define union types and functions
2. **Implement TestAndImproveBAML component** - Follow ToolCreator patterns
3. **Migrate ToolAssessor & ToolCorrector** - BAML implementations
4. **Update integration points** - Connect new components
5. **Comprehensive testing** - Validate end-to-end functionality
6. **Performance comparison** - Measure improvements vs DSPy

This migration establishes a clean, consistent pattern for BAML-based components with enhanced observability and performance.