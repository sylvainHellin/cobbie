import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any, Union


def get_element_properties_by_guid(
    ifc_file: ifcopenshell.file,
    element_guid: str,
    property_keywords: Optional[List[str]] = None,
    include_all_properties: bool = False,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Extracts comprehensive property information from a specific IFC element identified by its GUID.
    This function systematically explores all property sets of the target element and supports
    flexible property filtering using keywords.

    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_guid: GlobalId of the target element to analyze
        property_keywords: Optional list of keywords to filter properties (e.g., ['Width', 'Height', 'Area'] for dimensions)
        include_all_properties: Boolean to include all properties when keywords are specified (default: False)
        case_sensitive: Boolean for case-sensitive keyword matching (default: False)

    Returns:
        Dict containing:
            - 'element_info': Basic element information (type, name, object type)
            - 'found_properties': Dict of property sets and their matching properties
            - 'all_property_sets': Complete list of all property sets (when include_all_properties=True)
            - 'element_found': Boolean indicating if element was found

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = get_element_properties_by_guid(
        ...     model, 
        ...     '2XQ$n5SLP5MBLyL442paFx',
        ...     property_keywords=['Width', 'Height', 'Area']
        ... )
        >>> print(result['found_properties'])
    """
    # Initialize result structure
    result = {
        'element_info': {},
        'found_properties': {},
        'all_property_sets': {},
        'element_found': False
    }

    try:
        # Find element by GUID
        element = ifc_file.by_guid(element_guid)
        
        if element is None:
            return result
            
        result['element_found'] = True
        
        # Extract basic element information
        result['element_info'] = {
            'type': element.is_a(),
            'name': getattr(element, 'Name', None),
            'object_type': getattr(element, 'ObjectType', None),
            'global_id': getattr(element, 'GlobalId', None)
        }
        
        # Get all property sets using ifcopenshell utility
        all_psets = ifcopenshell.util.element.get_psets(element)
        
        if not all_psets:
            return result
            
        # Store all property sets if requested
        if include_all_properties:
            result['all_property_sets'] = all_psets
        
        # If no keywords specified, return all properties
        if not property_keywords:
            result['found_properties'] = all_psets
            return result
        
        # Filter properties based on keywords
        found_properties = {}
        
        for pset_name, pset_data in all_psets.items():
            matching_props = {}
            
            for prop_name, prop_value in pset_data.items():
                # Skip the 'id' field as it's internal metadata
                if prop_name == 'id':
                    continue
                    
                # Check if property name matches any keyword
                for keyword in property_keywords:
                    if case_sensitive:
                        if keyword in prop_name:
                            matching_props[prop_name] = prop_value
                            break
                    else:
                        if keyword.lower() in prop_name.lower():
                            matching_props[prop_name] = prop_value
                            break
            
            # Only include property sets that have matching properties
            if matching_props:
                found_properties[pset_name] = matching_props
        
        result['found_properties'] = found_properties
        
    except Exception as e:
        # In case of any error, return the current result with element_found=False
        result['element_found'] = False
        # Could add error information here if needed
        
    return result