import ifcopenshell
from typing import List, Dict, Any, Optional, Union


def find_elements_by_extreme_property(
    ifc_file,
    element_type: str,
    property_keywords: List[str],
    extreme_type: str = 'max',
    result_count: int = 5,
    case_sensitive: bool = False,
    min_value: float = 0,
    include_source: bool = True
) -> Dict[str, Any]:
    """
    Finds elements with extreme (minimum or maximum) quantitative properties from IFC models.
    
    This function handles the common BIM analysis pattern of identifying elements with the 
    largest or smallest values for specific properties like width, height, length, area, or volume. 
    It supports flexible property name matching across multiple languages and naming conventions.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcDoor', 'IfcWall', 'IfcWindow')
        property_keywords: List of property names to search for (e.g., ['Width', 'Breedte', 'DoorWidth'])
        extreme_type: 'max' or 'min' to find maximum or minimum values
        result_count: Number of top results to return (default: 5)
        case_sensitive: Whether property name matching should be case sensitive (default: False)
        min_value: Minimum valid value filter (default: 0)
        include_source: Whether to include property source information (default: True)
    
    Returns:
        Dict containing:
        - total_elements: Total number of elements found
        - elements_with_property: Number of elements with matching properties
        - ranked_elements: List of elements sorted by property value
        - property_name: The property name that was used for matching
        - extreme_value: The extreme value found
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = find_elements_by_extreme_property(
        ...     model, 'IfcDoor', ['Width', 'Breedte', 'DoorWidth'], 'max'
        ... )
        >>> print(f"Largest door width: {result['extreme_value']}")
    """
    try:
        # Validate inputs
        if extreme_type not in ['max', 'min']:
            raise ValueError("extreme_type must be 'max' or 'min'")
        
        if result_count < 1:
            raise ValueError("result_count must be at least 1")
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_elements = len(elements)
        
        if total_elements == 0:
            return {
                'total_elements': 0,
                'elements_with_property': 0,
                'ranked_elements': [],
                'property_name': None,
                'extreme_value': None
            }
        
        # Prepare property keywords for matching
        if not case_sensitive:
            property_keywords = [kw.lower() for kw in property_keywords]
        
        elements_with_values = []
        property_name_used = None
        
        # Process each element
        for element in elements:
            element_info = {
                'id': element.GlobalId,
                'name': element.Name,
                'object_type': getattr(element, 'ObjectType', None),
                'value': None,
                'source': None
            }
            
            # Search through all property sets
            for property_set in element.IsDefinedBy:
                if hasattr(property_set, 'RelatingPropertyDefinition'):
                    prop_def = property_set.RelatingPropertyDefinition
                    if hasattr(prop_def, 'HasProperties'):
                        for prop in prop_def.HasProperties:
                            if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                prop_name = prop.Name
                                prop_value = prop.NominalValue.wrappedValue
                                
                                # Check if property name matches keywords
                                prop_name_check = prop_name if case_sensitive else prop_name.lower()
                                
                                for keyword in property_keywords:
                                    keyword_check = keyword if case_sensitive else keyword.lower()
                                    
                                    if keyword_check in prop_name_check:
                                        # Check if value is numeric and valid
                                        if isinstance(prop_value, (int, float)) and prop_value >= min_value:
                                            # Update if this is a better value for the element
                                            if (element_info['value'] is None or 
                                                (extreme_type == 'max' and prop_value > element_info['value']) or
                                                (extreme_type == 'min' and prop_value < element_info['value'])):
                                                element_info['value'] = prop_value
                                                element_info['source'] = prop_name
                                                if property_name_used is None:
                                                    property_name_used = prop_name
                                        break
            
            # Only include elements that have a valid property value
            if element_info['value'] is not None:
                if not include_source:
                    del element_info['source']
                elements_with_values.append(element_info)
        
        elements_with_property = len(elements_with_values)
        
        if elements_with_property == 0:
            return {
                'total_elements': total_elements,
                'elements_with_property': 0,
                'ranked_elements': [],
                'property_name': None,
                'extreme_value': None
            }
        
        # Sort elements by value
        reverse_sort = (extreme_type == 'max')
        elements_with_values.sort(key=lambda x: x['value'], reverse=reverse_sort)
        
        # Get top results
        ranked_elements = elements_with_values[:result_count]
        extreme_value = ranked_elements[0]['value'] if ranked_elements else None
        
        return {
            'total_elements': total_elements,
            'elements_with_property': elements_with_property,
            'ranked_elements': ranked_elements,
            'property_name': property_name_used,
            'extreme_value': extreme_value
        }
        
    except Exception as e:
        # Return error information
        return {
            'total_elements': 0,
            'elements_with_property': 0,
            'ranked_elements': [],
            'property_name': None,
            'extreme_value': None,
            'error': str(e)
        }