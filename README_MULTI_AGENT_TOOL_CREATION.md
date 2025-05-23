# Multi-Agent Tool Creation System

## Overview

This system implements a multi-agent workflow for creating and testing Python functions (tools) that work with IFC files using the IfcOpenShell library. The key innovation is **unbiased testing** - the assessor agent tests the generated function without seeing its implementation code.

## Architecture

### Three Main Agents

1. **ToolCreator**: Generates Python functions based on requirements
2. **ToolAssessor** (Enhanced): Tests functions as tools without seeing implementation
3. **ToolCorrector**: Fixes issues identified during testing

### Key Components

#### Dynamic Tool Creation System

- **`extract_function_metadata()`**: Extracts function signature and docstring using AST parsing (no code execution)
- **`create_dynamic_tool()`**: Creates a callable wrapper around the generated function
- **`create_assessor_with_dynamic_tool()`**: Creates an enhanced assessor with the generated function as a tool

#### Unbiased Testing Approach

The system solves the bias problem through:

1. **Code Isolation**: The assessor never sees the implementation code
2. **Dynamic Tool Registration**: Generated functions are presented as tools with only their interface visible
3. **Behavioral Testing**: Assessment is based purely on function behavior, not implementation

## Technical Implementation

### How Unbiased Testing Works

```python
# 1. Extract only the interface (no implementation details)
metadata = extract_function_metadata(generated_code, function_name)

# 2. Create a dynamic tool wrapper
dynamic_tool = create_dynamic_tool(generated_code, function_name)

# 3. Present to assessor as a regular tool
enhanced_assessor = create_assessor_with_dynamic_tool(
    base_tools=[web_search, query_docs], 
    generated_code=code,
    function_name=name
)

# 4. Assessor can call the function but can't see implementation
assessment = enhanced_assessor(
    function_name=name,
    function_requirements=requirements,
    path_ifc_model=test_file
)
```

### Workflow

```
1. ToolCreator generates function code
2. System creates dynamic tool wrapper
3. Enhanced ToolAssessor tests function as tool
4. If issues found → ToolCorrector fixes them
5. Repeat until satisfactory (max 3 iterations)
```

## Usage

```python
from src.agents.create_new_tool import create_new_tool

requirements = """
Create a function that extracts all wall elements from an IFC file and returns 
their basic properties including name, type, height, and thickness.
"""

result = create_new_tool(
    requirements=requirements,
    path_ifc_model="path/to/test_model.ifc"
)

if result['status'] == 'success':
    print(f"Generated function: {result['function_name']}")
    print(result['function_code'])
```

## Benefits

1. **Unbiased Testing**: Assessor evaluates behavior, not implementation
2. **Higher Test Coverage**: No implementation bias leads to more comprehensive testing
3. **Iterative Improvement**: Automatic correction based on test results
4. **Real-world Testing**: Uses actual IFC files for validation
5. **Robust Error Handling**: Graceful handling of failures at each step

## Research Backing

This approach is based on research showing that test coverage increases when testers don't see the implementation code, as they're forced to test based on requirements rather than implementation details.

## Future Enhancements

- Support for multiple test IFC files
- More sophisticated function name extraction from requirements
- Integration with external test databases
- Metrics collection for assessment quality
- Support for more complex function signatures 