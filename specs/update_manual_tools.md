# Implementation Plan: Refactor Manual Tools to Use model_path Parameter

## Overview
Refactor 25 tools in `src/tools/manual/` to remove dependency on the deprecated `state` module and use an explicit `model_path: str` parameter instead.

## Scope
- **Tools to modify:** 25 out of 26 tools
- **Excluded:** `calculator.py` (does not use state or model)

## Changes Required Per Tool

### 1. Remove State Import
**Delete lines:**
```python
# state management
from state import get_model_path
```

### 2. Update Function Signature
**Place `model_path` as FIRST required parameter**

Before:
```python
def function_name(model: str = None, other_param: type = None) -> return_type:
```

After:
```python
def function_name(model_path: str, other_param: type = None) -> return_type:
```

**For tools with model parameter last** (e.g., room_ceiling_height):
Before:
```python
def room_ceiling_height(name: str = None, guid: str = None, model: str = None):
```

After:
```python
def room_ceiling_height(model_path: str, name: str = None, guid: str = None):
```

### 3. Update IFC Model Loading
Before:
```python
ifc_model = ifcopenshell.open(get_model_path(model=model))
```

After:
```python
ifc_model = ifcopenshell.open(model_path)
```

### 4. Update Docstring
Before:
```python
Args:
    model (str, optional): The type of model to analyze - e.g. 'arc' for architectural
        or 'mep' for MEP model. If None, uses the model from the current state.
```

After:
```python
Args:
    model_path (str): Absolute path to the IFC model file to analyze.
```

### 5. Remove Test Block
Delete entire `if __name__ == "__main__":` section

### 6. Remove sys path
- Remove `sys.path.insert(0, os.path.dirname(os.getcwd()))`

## Tools to Update (25)

### Batch 1: Simple Read-Only Tools (5)
1. `get_storeys_names.py`
2. `is_georeferenced.py`
3. `find_elements_by_ifc_class.py` - Example tool, standard pattern
4. `list_object_types_for_ifc_entity.py`
5. `get_type_definitions_and_instances.py`

### Batch 2: Property/Dimension Tools (5)
6. `get_element_properties.py`
7. `get_door_dimensions.py`
8. `get_element_bounding_box.py`
9. `get_element_material_layers_and_thicknesses.py`
10. `get_floor_to_floor_height.py`

### Batch 3: Area/Volume Calculations (6)
11. `calculate_glazing_area.py`
12. `calculate_gross_floor_area.py`
13. `calculate_usable_floor_area.py`
14. `get_elements_area.py`
15. `get_elements_volume.py`
16. `get_pipe_length_by_type.py`

### Batch 4: Room/Space Tools (6)
17. `list_rooms.py`
18. `room_ceiling_height.py` - Model parameter last, needs reordering
19. `get_elements_in_room.py`
20. `get_containing_rooms_for_entities_type.py` - Model parameter last
21. `get_containing_rooms_for_entity_guids.py` - Model parameter last
22. `get_rooms_with_outdoor_access.py`

### Batch 5: Analysis Tools (3)
23. `analyze_elements_exterior_classification.py`
24. `check_door_accessibility.py`
25. `count_windows_on_facade.py`

## Validation Process

After each batch:
1. **Syntax check:** `uvx ruff check src/tools/manual/<filename>.py`
2. **Type check:** `uvx ty check src/tools/manual/<filename>.py`
3. **Static analysis:** `uvx pyright src/tools/manual/<filename>.py`
4. **Manual verification:**
   - No `from state import` remains
   - `model_path: str` is first required parameter
   - No `get_model_path()` calls remain
   - Test block removed
   - Docstring updated

## Key Files

**Critical files to modify:**
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/src/tools/manual/find_elements_by_ifc_class.py` - Reference pattern
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/src/tools/manual/room_ceiling_height.py` - Parameter reordering example
- All 23 other tools following similar patterns

**File to leave unchanged:**
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/src/tools/manual/calculator.py` - No state dependency

## Example Transformation

**Before (find_elements_by_ifc_class.py):**
```python
# state management
from state import get_model_path

def find_elements_by_ifc_class(model: str = None, element_type: str = None) -> str:
    """Retrieves basic information about all elements of a specified IFC type from the model.

    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural
            or 'mep' for MEP model. If None, uses the model from the current state.
        element_type (str): The IFC entity type to search for...
    """
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    # ... rest of function

if __name__ == "__main__":
    print(find_elements_by_ifc_class(model="arc", element_type="IfcWall"))
```

**After:**
```python
# (state import removed)

def find_elements_by_ifc_class(model_path: str, element_type: str = None) -> str:
    """Retrieves basic information about all elements of a specified IFC type from the model.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        element_type (str, optional): The IFC entity type to search for...
    """
    ifc_model = ifcopenshell.open(model_path)
    # ... rest of function

# (test block removed)
```

## Assumptions
1. All tools follow consistent import patterns
2. Each tool uses `get_model_path()` exactly once in main function
3. No downstream code directly imports these manual tools (they're invoked via `execute_python()`)
4. The `execute_python()` context will provide `path_ifc_model` for LLM-generated code to use

## Success Criteria
- All 25 tools pass linters (ruff, ty, pyright)
- No state module imports remain
- All tools accept `model_path: str` as required first parameter
- All test blocks removed
- Docstrings updated correctly
