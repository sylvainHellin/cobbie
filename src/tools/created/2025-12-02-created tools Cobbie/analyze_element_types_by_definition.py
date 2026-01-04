import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any

def analyze_element_types_by_definition(
    ifc_file,
    element_type: str,
    include_untyped: bool = True,
    include_examples: int = 3,
    case_sensitive: bool = False,
    max_elements: int = 1000
) -> Dict[str, Any]:
    """
    Analyzes IFC elements by their type definitions (IsTypedBy relationships) and provides counts by type.
    
    This function handles the common BIM analysis task of understanding how elements are classified
    through type definitions rather than properties or naming conventions.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcDoor', 'IfcWindow')
        include_untyped: Whether to include elements without type definitions in results (default True)
        include_examples: Number of example elements to include for each type (default 3)
        case_sensitive: Whether string comparisons should be case sensitive (default False)
        max_elements: Maximum number of elements to analyze (default 1000)
    
    Returns:
        Dict with 'total_elements', 'typed_elements', 'untyped_elements', 'type_counts' 
        (dict mapping type names to counts), and 'type_examples' (dict mapping type names to 
        example element names).
    
    Example usage:
        import ifcopenshell
        model = ifcopenshell.open('building.ifc')
        result = analyze_element_types_by_definition(model, 'IfcWall')
        print(f"Found {result['total_elements']} walls")
        for wall_type, count in result['type_counts'].items():
            print(f"  {wall_type}: {count} walls")
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Limit the number of elements to analyze
        if len(elements) > max_elements:
            elements = elements[:max_elements]
        
        total_elements = len(elements)
        type_counts = {}
        type_examples = {}
        typed_elements = 0
        untyped_elements = 0
        
        for element in elements:
            try:
                # Get the type definition for this element
                element_type_def = ifcopenshell.util.element.get_type(element)
                
                if element_type_def is not None:
                    # Element has a type definition
                    type_name = element_type_def.Name if hasattr(element_type_def, 'Name') and element_type_def.Name else 'Unnamed Type'
                    
                    # Apply case sensitivity setting
                    if not case_sensitive:
                        type_name = type_name.lower()
                    
                    # Update count
                    if type_name not in type_counts:
                        type_counts[type_name] = 0
                        type_examples[type_name] = []
                    
                    type_counts[type_name] += 1
                    typed_elements += 1
                    
                    # Add example if needed
                    if len(type_examples[type_name]) < include_examples:
                        element_name = element.Name if hasattr(element, 'Name') and element.Name else 'No Name'
                        type_examples[type_name].append(element_name)
                        
                else:
                    # Element has no type definition
                    untyped_elements += 1
                    
                    if include_untyped:
                        type_name = 'No Type Defined'
                        if type_name not in type_counts:
                            type_counts[type_name] = 0
                            type_examples[type_name] = []
                        
                        type_counts[type_name] += 1
                        
                        if len(type_examples[type_name]) < include_examples:
                            element_name = element.Name if hasattr(element, 'Name') and element.Name else 'No Name'
                            type_examples[type_name].append(element_name)
                            
            except Exception as e:
                # Handle individual element errors gracefully
                untyped_elements += 1
                if include_untyped:
                    type_name = 'Error Processing'
                    if type_name not in type_counts:
                        type_counts[type_name] = 0
                        type_examples[type_name] = []
                    type_counts[type_name] += 1
        
        return {
            'total_elements': total_elements,
            'typed_elements': typed_elements,
            'untyped_elements': untyped_elements,
            'type_counts': type_counts,
            'type_examples': type_examples
        }
        
    except Exception as e:
        # Return error information
        return {
            'total_elements': 0,
            'typed_elements': 0,
            'untyped_elements': 0,
            'type_counts': {'Error': str(e)},
            'type_examples': {'Error': []}
        }