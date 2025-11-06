import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional

def count_elements_by_type(
    ifc_file,
    element_type: str,
    type_property_names: Optional[List[str]] = None,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Counts and categorizes IFC elements of a specified type by extracting type information 
    from multiple sources. This function is designed to answer questions like 'how many 
    elements of type X exist and what are their subtypes?'. It intelligently extracts type 
    information from Name, ObjectType, and property sets with fallback logic.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcRailing', 'IfcDoor', 'IfcWindow')
        type_property_names: Optional list of property names to check for type information 
                           (defaults to ['Classification Description', 'Reference', 'Type'])
        include_details: Optional boolean to include detailed element information in results 
                        (default False)
    
    Returns:
        Dict[str, Any]: Dictionary with structure:
        {
            'total_count': int,
            'type_counts': Dict[str, int],
            'elements_by_type': Dict[str, List[Dict]] (if include_details=True)
        }
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = count_elements_by_type(model, 'IfcRailing')
        >>> print(f"Total: {result['total_count']}")
        >>> print(f"Types: {result['type_counts']}")
    """
    try:
        # Set default property names if not provided
        if type_property_names is None:
            type_property_names = ['Classification Description', 'Reference', 'Type']
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Initialize result structures
        type_counts: Dict[str, int] = {}
        elements_by_type: Dict[str, List[Dict]] = {}
        
        for element in elements:
            # Initialize element info for detailed output
            element_info = {
                'id': element.id(),
                'name': element.Name or 'N/A',
                'object_type': element.ObjectType or 'N/A',
                'predefined_type': getattr(element, 'PredefinedType', None) or 'N/A'
            }
            
            # Determine element type with fallback logic
            determined_type = 'Unknown'
            
            # Try to get property sets
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Check property sets for type information in priority order
                for prop_name in type_property_names:
                    for pset_name, pset_properties in psets.items():
                        if prop_name in pset_properties:
                            prop_value = pset_properties[prop_name]
                            if prop_value and prop_value != 'N/A' and str(prop_value).strip():
                                determined_type = str(prop_value)
                                element_info[f'found_in_{prop_name}'] = determined_type
                                break
                    if determined_type != 'Unknown':
                        break
                        
            except Exception as e:
                # Continue with basic attributes if property sets fail
                pass
            
            # Fallback to ObjectType if still unknown
            if determined_type == 'Unknown' and element.ObjectType:
                determined_type = element.ObjectType
                element_info['found_in_ObjectType'] = determined_type
            
            # Fallback to Name if still unknown
            if determined_type == 'Unknown' and element.Name:
                determined_type = element.Name
                element_info['found_in_Name'] = determined_type
            
            # Final fallback to element type
            if determined_type == 'Unknown':
                determined_type = element_type
                element_info['found_in_fallback'] = determined_type
            
            # Update counts
            if determined_type not in type_counts:
                type_counts[determined_type] = 0
                if include_details:
                    elements_by_type[determined_type] = []
            
            type_counts[determined_type] += 1
            
            # Add detailed info if requested
            if include_details:
                elements_by_type[determined_type].append(element_info)
        
        # Build result
        result: Dict[str, Any] = {
            'total_count': len(elements),
            'type_counts': type_counts
        }
        
        if include_details:
            result['elements_by_type'] = elements_by_type
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'total_count': 0,
            'type_counts': {},
            'error': f"Error processing {element_type}: {str(e)}"
        }