# Migration Plan : from DSPY to BAML

## Overview
Migrate from DSPy to BAML using union types for elegant handling of CodeAct modes. This plan focuses on building a working BAML alternative first, then cleaning up DSPy code later.

## Phase 1: BAML Foundation with Union Types

### Step 1.1: Update BAML Clients for GLM 4.6
**Add to `baml_src/clients.baml`:**
```baml
client<llm> ZAIGLM46 {
  provider openai
  options {
    model "glm-4.6"
    api_key env.Z_AI_API_KEY
    base_url "https://api.z.ai/api/paas/v4/chat/completions"
  }
}

client<llm> ZAIGLM46Mini {
  provider openai
  retry_policy Exponential
  options {
    model "glm-4.6-mini"
    api_key env.Z_AI_API_KEY
    base_url "https://api.z.ai/api/paas/v4/chat/completions"
  }
}
```

### Step 1.2: Define Union Type Schemas
**Create `baml_src/schemas.baml`:**
```baml
// Code execution action (loop mode)
class CodeAction {
  thoughts string @description("Reasoning for next step")
  python_code string @description("Code to execute")
}

// Final answer action (completion mode)
class FinalAnswer {
  thoughts string @description("Summary of findings")
  answer string @description("Final answer to user's question")
}

// Tool creation result
class ToolCreationResult {
  function_name string
  function_implementation string
  success bool
}

// Answer verification result
class SimilarityResult {
  similarity_score float
  correct_answer bool
  reasoning string
}

// Error analysis result
class ErrorAnalysisResult {
  error_category string @description("faulty_tool, missing_tool, other")
  function_name string?
  needs_new_tool bool
}

// Tool optimization result
class ToolOptimizationResult {
  improvement string @description("create_new_tool, merge_existing_tools, update_existing_tool, no_action_needed")
  function_name string?
  function_requirements string?
  existing_tool_names string[]?
}
```

## Phase 2: CodeAct implementation

### Step 2.1: CodeAct Union Function
**Create `baml_src/code_act.baml`:**
```baml
// Single function that returns either CodeAction (continue) or FinalAnswer (stop)
function BIMQAS(
  user_input: string,
  available_tools: string,
  previous_attempts: string? @description("Previous execution results, if any")
) -> CodeAction | FinalAnswer {
  client ZAIGLM46
  prompt #"
    {{ _.role("system") }}
    Instructions:
    You are a helpful assistant specialising in retrieving information from BIM models using Python code and the IfcOpenShell library. To facilitate this task, you also have access to higher-level functions that will help you with the most common information retrieval tasks (referred to later as the 'tools'). These tools can be used directly in your Python code as they are already pre-loaded; there is no need to import them.

    When a user asks a question, you can either:
    1. Write Python code to investigate further (returns CodeAction)
    2. Provide the final answer if you have sufficient information (returns FinalAnswer)

    Question:
    {{ user_input }}

    Tools:
    {{ available_tools }}

    {% if previous_attempts %}
    Previous Results:
    {{ previous_attempts }}
    {% endif %}

    Now, choose your next action (only one):
    - CodeAction: If you need to explore/analyze more with Python code
    - FinalAnswer: If you have enough information to answer completely

    {{ ctx.output_format }}
  "#
}
```

### Step 2.2: Thin Python Orchestration
**Create NEW file `src/engine/components/bim_qas.py`:**
```python
from typing import Callable, List, Dict, Any, Optional
import mlflow
from baml_client import b
from baml_client.types import CodeAction, FinalAnswer

class BIMQAS:
    """BAML-based alternative to DSPy Engine"""

    def __init__(self, tools: List[Callable] = None, max_iterations: int = 10):
        self.tools = tools or []
        self.max_iterations = max_iterations
        self._setup_interpreter()

    def _setup_interpreter(self):
        # Setup interpreter with MLflow tracing decorator
        from src.engine.util.mlflow_tracing import trace_python_interpreter
        base_interpreter = get_python_interpreter(
            additional_authorized_functions={t.__name__: t for t in self.tools}
        )
        self.python_interpreter = trace_python_interpreter(base_interpreter)

    def _generate_tools_docs(self) -> str:
        """Generate tool documentation for prompts"""
        docs = []
        for tool in self.tools:
            import inspect
            sig = inspect.signature(tool)
            docstring = inspect.getdoc(tool) or "No documentation"
            docs.append(f"def {tool.__name__}{sig}:\n    '''{docstring}'''")
        return "\n\n".join(docs)

    @mlflow.trace("code_act_baml_execution")
    async def run(self, user_input: str, task_instructions: str) -> Dict[str, Any]:
        """Orchestration layer for the CodeAct logic"""

        previous_results = []
        tools_docs = self._generate_tools_docs()

        for iteration in range(self.max_iterations):
            # Next action depends on the returned type defined with BAML
            previous_context = "\n".join(previous_results[-3:])  # Last 3 results

            result = await b.BIMQAS(
                user_input=user_input,
                task_instructions=task_instructions,
                available_tools=tools_docs,
                previous_attempts=previous_context if previous_results else None
            )

            # Check the returned type to determine action
            if isinstance(result, CodeAction):
                # Execute code and continue
                try:
                    output = self.python_interpreter(python_code=result.python_code)
                    previous_results.append(f"Code: {result.python_code}\nResult: {output}")
                except Exception as e:
                    previous_results.append(f"Code: {result.python_code}\nError: {str(e)}")

            elif isinstance(result, FinalAnswer):
                # Done! Type checking tells us we're finished
                return {
                    "status": "success",
                    "answer": result.answer,
                    "iterations": iteration + 1,
                    "reasoning": result.thoughts
                }

        # Max iterations reached
        return {
            "status": "incomplete",
            "iterations": self.max_iterations,
            "last_result": previous_results[-1] if previous_results else "No results"
        }
```

## Goal of the migration

1. **Type Safety**: Union types with `isinstance()` checking eliminate need for mode fields
2. **Thin Python**: Orchestration layer is minimal - just routing and execution
3. **Parallel Development**: Keep existing DSPy code while building BAML alternative
4. **Elegant Logic**: BAML union types handle mode decisions cleanly
5. **Built-in Features**: BAML handles retries, error handling
6. **Clear Separation**: BAML handles decision logic, Python handles execution

## Implementation Checklist

### Phase 1: Foundation
- [ ] Update `baml_src/clients.baml` with correct GLM 4.6 API endpoints
- [ ] Define union type schemas in `baml_src/schemas.baml` (no mode fields)
- [ ] Create `BIMQAS` function with `CodeAction | FinalAnswer` union
- [ ] Regenerate BAML client: `uv run baml-cli generate`

### Phase 2: Core BAML Alternative
- [ ] Create `src/engine/components/bim_qas.py`
- [ ] Test union type behavior with `isinstance()` checking
- [ ] Verify MLflow tracing works with union types
- [ ] Run basic functionality tests

## Key Design Decisions

1. **No Mode Fields**: Use `isinstance()` to check returned union types instead of mode fields
2. **Parallel Development**: Keep DSPy code until BAML alternative is working
3. **Thin Orchestration**: Python just routes and executes, BAML handles all decision logic
4. **Correct API Details**: Use GLM 4.6 with `Z_AI_API_KEY` and correct endpoint
5. **MLflow Integration**: Simple decorators that log result types for union types
