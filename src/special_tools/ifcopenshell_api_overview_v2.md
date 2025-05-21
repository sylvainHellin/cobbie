## 1. API Structure

### Main Modules and Their Purposes
- **ifcopenshell** - Core package for IFC file operations
  - **file** - IFC file management
  - **entity_instance** - Base class for all IFC entities
  - **guid** - Utilities for handling IFC GlobalId
- **ifcopenshell.util** - Utility functions for common operations
  - **selector** - Query syntax for filtering elements
  - **unit** - Unit conversion
  - **pset** - Property set handling
  - **element** - Element information retrieval
- **ifcopenshell.geom** - Geometry processing
  - **main** - Core geometry operations

### Key Classes
- **ifcopenshell.file.file** - Primary container for IFC models
- **ifcopenshell.entity_instance.entity_instance** - Base class for IFC entities
- **ifcopenshell.geom.main.settings** - Configuration for geometry operations
- **ifcopenshell.geom.main.iterator** - Efficient traversal of geometric data

## 2. Common Information Retrieval Operations

### Loading IFC Files
```python
import ifcopenshell
# Open an existing IFC file
model = ifcopenshell.open('/path/to/model.ifc')
# Check schema version
print(model.schema)  # Returns IFC2X3, IFC4, etc.
```

### Querying Elements
```python
# Get elements by type
walls = model.by_type("IfcWall")
# Get element by GlobalId
element = model.by_guid('0EI0MSHbX9gg8Fxwar7lL8')
# Get element by ID
element = model.by_id(1)

# Using selector utility for complex queries
import ifcopenshell.util.selector
selector = ifcopenshell.util.selector.Selector()
# Simple type selection
walls = selector.parse(model, '.IfcWall')
# Complex query with conditions
fire_rated_walls = selector.parse(model, '.IfcWall[Pset_WallCommon.FireRating = "2HR"]')
# Combining queries
elements = selector.parse(model, '.IfcWall | .IfcSlab')  # Walls OR slabs
```

### Accessing Properties
```python
# Direct attribute access
wall = model.by_type("IfcWall")[0]
print(wall.Name)
print(wall.GlobalId)

# Get all attributes as dictionary
wall_info = wall.get_info()

# Access property sets
import ifcopenshell.util.element
props = ifcopenshell.util.element.get_psets(wall)
fire_rating = props.get("Pset_WallCommon", {}).get("FireRating")
```

### Traversing Relationships
```python
# Get all related elements
related_elements = model.get_inverse(wall)

# Get building storey containing a wall
for rel in wall.ContainedInStructure:
    storey = rel.RelatingStructure
    print(f"Wall is on level: {storey.Name}")

# Get materials assigned to an element
materials = []
for rel in wall.HasAssociations:
    if rel.is_a("IfcRelAssociatesMaterial"):
        materials.append(rel.RelatingMaterial)
```

## 3. Geometry Processing

### Basic Geometry Operations
```python
import ifcopenshell.geom

# Configure geometry settings
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)
settings.set(settings.INCLUDE_CURVES, True)

# Process geometry for a single element
wall = model.by_type("IfcWall")[0]
shape = ifcopenshell.geom.create_shape(settings, wall)

# Access geometry data
vertices = shape.geometry.verts  # Flat list of vertices
faces = shape.geometry.faces     # List of face indices
materials = shape.geometry.materials  # Material information
```

### Efficient Geometry Processing with Iterator
```python
# Create iterator for processing large models
settings = ifcopenshell.geom.settings()
iterator = ifcopenshell.geom.main.iterator(settings, model, num_threads=4)

while iterator.next():
    # Process one element at a time
    shape = iterator.get()
    # Access element information
    element = shape.product
    print(f"Processing {element.is_a()}: {element.Name}")
    # Access geometry data
    vertices = shape.geometry.verts
    faces = shape.geometry.faces
    # Perform analysis or extraction operations
```

### Filtering Geometry
```python
# Process only specific element types
iterator = ifcopenshell.geom.main.iterator(
    settings, model,
    include=["IfcWall", "IfcSlab"],  # Only process these types
    exclude=["#123", "#456"]  # Exclude specific elements
)
```

## 4. Performance Considerations

### Best Practices
1. **Use type filtering early** - Filter by element type at the model level
2. **Batch geometry processing** - Use iterators instead of processing one element at a time
3. **Implement memory management** - Process and release geometry data in batches

### Handling Large Models
```python
# Use HDF5 caching for large geometry operations
settings = ifcopenshell.geom.settings()
iterator = ifcopenshell.geom.main.iterator(
    settings, model, num_threads=4, cache="cache.h5"
)
```

### Common Pitfalls
1. **Null attribute access** - Always check if attributes exist before accessing
   ```python
   # Safe access pattern
   storey_name = None
   if element.ContainedInStructure:
       relating_structure = element.ContainedInStructure[0].RelatingStructure
       if relating_structure:
           storey_name = relating_structure.Name
   ```

2. **Schema differences** - Handle schema variations
   ```python
   if model.schema == "IFC4":
       # Use IFC4-specific approach
   elif model.schema == "IFC2X3":
       # Use IFC2X3-specific approach
   ```

## 5. Sample Information Retrieval Function

```python
def get_element_properties(model, element_id, property_set_name=None):
    """Get properties of an element, optionally filtered by property set name."""
    try:
        # Handle different input types
        if isinstance(element_id, int):
            element = model.by_id(element_id)
        elif isinstance(element_id, str) and len(element_id) == 22:
            element = model.by_guid(element_id)
        else:
            raise ValueError(f"Invalid element identifier: {element_id}")

        # Get properties
        all_psets = ifcopenshell.util.element.get_psets(element)

        # Filter by property set if specified
        if property_set_name:
            return all_psets.get(property_set_name, {})
        return all_psets
    except Exception as e:
        print(f"Error getting properties: {e}")
        return None
```
