import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def count_elements_in_space_by_keywords(
    ifc_file: ifcopenshell.file,
    element_type: str,
    space_identifier: str,
    element_keywords: List[str],
    search_fields: List[str] = ['Name', 'ObjectType'],
    case_sensitive: bool = False,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Counts elements of a specified type that are contained within a specific space/room,
    using semantic keyword filtering for element identification.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcEnergyConversionDevice', 'IfcFlowTerminal')
        space_identifier: Name or identifier of the target space/room (e.g., 'A202', 'Room 101')
        element_keywords: List of keywords to identify target elements (e.g., ['radiator', 'heater'])
        search_fields: List of fields to search for keywords (default: ['Name', 'ObjectType'])
        case_sensitive: Whether keyword matching should be case sensitive (default: False)
        include_details: Whether to include details of found elements (default: False)
    
    Returns:
        Dict with count, space info, and optional element details:
        {
            'count': int,
            'space_found': bool,
            'space_info': Dict[str, Any],
            'elements': List[Dict[str, Any]] (if include_details=True),
            'total_elements_in_model': int,
            'matching_spaces': List[Dict[str, Any]] (all spaces that matched the identifier)
        }
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = count_elements_in_space_by_keywords(
        ...     model, 'IfcEnergyConversionDevice', 'A202', ['radiator']
        ... )
        >>> print(result['count'])
    """
    try:
        # Initialize result structure
        result = {
            'count': 0,
            'space_found': False,
            'space_info': {},
            'elements': [],
            'total_elements_in_model': 0,
            'matching_spaces': []
        }
        
        # Find ALL spaces that match the identifier
        matching_spaces = []
        for space in ifc_file.by_type('IfcSpace'):
            space_name = getattr(space, 'Name', None) or ''
            space_longname = getattr(space, 'LongName', None) or ''
            
            if space_identifier in space_name or space_identifier in space_longname:
                space_info = {
                    'id': space.id(),
                    'name': space_name,
                    'longname': space_longname,
                    'type': space.is_a(),
                    'space_object': space
                }
                matching_spaces.append(space_info)
        
        result['matching_spaces'] = [{k: v for k, v in s.items() if k != 'space_object'} for s in matching_spaces]
        
        if not matching_spaces:
            return result
        
        result['space_found'] = True
        result['space_info'] = result['matching_spaces'][0]  # Primary match
        
        # Get all elements of the specified type
        all_elements = list(ifc_file.by_type(element_type))
        result['total_elements_in_model'] = len(all_elements)
        
        # Filter elements by keywords
        matching_elements = []
        for element in all_elements:
            element_matches = False
            
            # Check each search field for keywords
            for field in search_fields:
                if hasattr(element, field):
                    field_value = getattr(element, field)
                    if field_value:
                        search_text = field_value if case_sensitive else field_value.lower()
                        
                        for keyword in element_keywords:
                            search_keyword = keyword if case_sensitive else keyword.lower()
                            if search_keyword in search_text:
                                element_matches = True
                                break
                    
                    if element_matches:
                        break
            
            if element_matches:
                matching_elements.append(element)
        
        # Check spatial containment for matching elements against ALL matching spaces
        elements_in_space = []
        for element in matching_elements:
            try:
                container = ifcopenshell.util.element.get_container(element)
                # Check if container matches any of our target spaces
                for space_info in matching_spaces:
                    if container == space_info['space_object']:
                        elements_in_space.append(element)
                        
                        if include_details:
                            element_info = {
                                'id': element.id(),
                                'type': element.is_a(),
                                'name': getattr(element, 'Name', None),
                                'object_type': getattr(element, 'ObjectType', None),
                                'space_name': space_info['name'],
                                'space_id': space_info['id']
                            }
                            result['elements'].append(element_info)
                        break
                        
            except Exception:
                # If get_container fails, try manual relationship traversal
                for rel in ifc_file.get_inverse(element):
                    if rel.is_a('IfcRelContainedInSpatialStructure'):
                        if hasattr(rel, 'RelatingStructure'):
                            for space_info in matching_spaces:
                                if rel.RelatingStructure == space_info['space_object']:
                                    elements_in_space.append(element)
                                    
                                    if include_details:
                                        element_info = {
                                            'id': element.id(),
                                            'type': element.is_a(),
                                            'name': getattr(element, 'Name', None),
                                            'object_type': getattr(element, 'ObjectType', None),
                                            'space_name': space_info['name'],
                                            'space_id': space_info['id']
                                        }
                                        result['elements'].append(element_info)
                                    break
                            break
        
        result['count'] = len(elements_in_space)
        return result
        
    except Exception as e:
        return {
            'count': 0,
            'space_found': False,
            'space_info': {},
            'elements': [],
            'total_elements_in_model': 0,
            'matching_spaces': [],
            'error': str(e)
        }