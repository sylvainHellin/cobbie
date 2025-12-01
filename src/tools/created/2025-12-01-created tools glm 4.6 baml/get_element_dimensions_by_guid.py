import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def get_element_dimensions_by_guid(
    ifc_file: ifcopenshell.file,
    element_guid: str,
    property_set_filter: Optional[List[str]] = None,
    dimension_property_names: Optional[List[str]] = None,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Extracts dimensional properties from a specific IFC element identified by its GUID.
    
    This function handles the common BIM analysis pattern of finding elements by their 
    unique identifier and extracting width, height, length, area, volume, and other 
    dimensional measurements from property sets. It supports flexible property name 
    matching and handles various property value types.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_guid: GUID of the target element
        property_set_filter: Optional list of property set names to search in 
                           (default: all property sets)
        dimension_property_names: List of property names to extract 
                                 (default: common dimensional names like 
                                 'Width', 'Height', 'Length', 'Area', 'Volume')
        case_sensitive: Whether property name matching should be case sensitive 
                       (default: False)
    
    Returns:
        Dict containing element info and extracted dimensional properties 
        with their values and sources. Structure:
        {
            'element_found': bool,
            'element_info': {
                'id': int,
                'type': str,
                'name': str,
                'guid': str
            },
            'dimensions': {
                'property_name': {
                    'value': Union[float, int, str],
                    'source_pset': str,
                    'unit': Optional[str]
                }
            },
            'available_property_sets': List[str],
            'errors': List[str]
        }
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = get_element_dimensions_by_guid(
        ...     model, 
        ...     '0otfaO0qPDAhynjJ6DmgH8',
        ...     dimension_property_names=['Height', 'Width']
        ... )
        >>> print(result['dimensions']['Height']['value'])
        1.735
    """
    # Initialize result structure
    result = {
        'element_found': False,
        'element_info': {},
        'dimensions': {},
        'available_property_sets': [],
        'errors': []
    }
    
    # Set default dimension property names if not provided
    if dimension_property_names is None:
        dimension_property_names = [
            'Width', 'Height', 'Length', 'Depth', 'Thickness',
            'Area', 'Volume', 'Perimeter', 'NominalWidth', 'NominalHeight',
            'NominalLength', 'OverallWidth', 'OverallHeight', 'OverallLength'
        ]
    
    try:
        # Find element by GUID
        element = ifc_file.by_guid(element_guid)
        if element is None:
            result['errors'].append(f"Element with GUID '{element_guid}' not found")
            return result
        
        # Populate element info
        result['element_found'] = True
        result['element_info'] = {
            'id': element.id(),
            'type': element.is_a(),
            'name': getattr(element, 'Name', ''),
            'guid': element_guid
        }
        
        # Get all property sets
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            result['available_property_sets'] = list(psets.keys())
        except Exception as e:
            result['errors'].append(f"Failed to retrieve property sets: {str(e)}")
            return result
        
        # Filter property sets if specified
        if property_set_filter:
            if case_sensitive:
                filtered_psets = {k: v for k, v in psets.items() 
                                 if k in property_set_filter}
            else:
                filter_lower = [name.lower() for name in property_set_filter]
                filtered_psets = {k: v for k, v in psets.items() 
                                 if k.lower() in filter_lower}
            psets = filtered_psets
        
        # Search for dimensional properties
        for pset_name, pset_data in psets.items():
            if not isinstance(pset_data, dict):
                continue
                
            for prop_name, prop_value in pset_data.items():
                # Skip the 'id' field which is metadata
                if prop_name == 'id':
                    continue
                
                # Check if this property name matches any of our target dimensions
                prop_name_match = None
                if case_sensitive:
                    if prop_name in dimension_property_names:
                        prop_name_match = prop_name
                else:
                    prop_lower = prop_name.lower()
                    for target_name in dimension_property_names:
                        if prop_lower == target_name.lower():
                            prop_name_match = target_name
                            break
                
                if prop_name_match:
                    # Extract the value and determine its type
                    value = prop_value
                    unit = None
                    
                    # Try to infer unit based on property name
                    prop_lower = prop_name.lower()
                    if any(dim in prop_lower for dim in ['width', 'height', 'length', 'depth', 'thickness']):
                        unit = 'm'
                    elif 'area' in prop_lower:
                        unit = 'm²'
                    elif 'volume' in prop_lower:
                        unit = 'm³'
                    elif 'perimeter' in prop_lower:
                        unit = 'm'
                    
                    result['dimensions'][prop_name_match] = {
                        'value': value,
                        'source_pset': pset_name,
                        'unit': unit
                    }
        
    except Exception as e:
        result['errors'].append(f"Unexpected error: {str(e)}")
    
    return result