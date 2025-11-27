import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Union, Optional, Any


def get_elements_in_space(
    ifc_file: ifcopenshell.file,
    space_identifier: Union[int, str],
    element_types: List[str],
    include_space_info: bool = True,
    include_element_properties: bool = False,
    property_sets: Optional[List[str]] = None,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Retrieves IFC elements of specified types that are spatially contained within a target space.
    
    This function handles the common BIM analysis pattern of finding elements by type 
    within a specific spatial container, with optional property extraction for both 
    elements and the space.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        space_identifier: Space identifier (can be ID, GlobalId, or name)
        element_types: List of IFC element types to search for (e.g., ['IfcFurniture', 'IfcDoor'])
        include_space_info: Boolean to include basic space information (default: True)
        include_element_properties: Boolean to include element properties (default: False)
        property_sets: Optional list of property sets to extract (default: None for all)
        case_sensitive: Boolean for name matching (default: False)
    
    Returns:
        Dict containing:
        - 'space': Dict with space basic information (Name, LongName, GlobalId, etc.)
        - 'elements': List of element dicts with basic info and optional properties
        - 'count': Total number of elements found
        - 'element_types_found': List of element types that had matches
        
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = get_elements_in_space(
        ...     model, 
        ...     'Kitchen', 
        ...     ['IfcFurniture'],
        ...     include_element_properties=True
        ... )
        >>> print(f"Found {result['count']} furniture items")
        >>> for element in result['elements']:
        ...     print(f"- {element['Name']}")
    """
    try:
        # Initialize result structure
        result = {
            'space': {},
            'elements': [],
            'count': 0,
            'element_types_found': []
        }
        
        # Find the target space
        target_space = None
        
        if isinstance(space_identifier, int):
            # Search by ID
            try:
                target_space = ifc_file[space_identifier]
                if target_space.is_a() != 'IfcSpace':
                    target_space = None
            except:
                pass
        
        if target_space is None:
            # Search by GlobalId or name
            for space in ifc_file.by_type('IfcSpace'):
                if space.GlobalId == str(space_identifier):
                    target_space = space
                    break
                
                name_match = space.Name == str(space_identifier) if case_sensitive else space.Name.lower() == str(space_identifier).lower()
                long_name_match = space.LongName == str(space_identifier) if case_sensitive else space.LongName.lower() == str(space_identifier).lower() if space.LongName else False
                
                if name_match or long_name_match:
                    target_space = space
                    break
        
        if target_space is None:
            raise ValueError(f"Space '{space_identifier}' not found in the IFC model")
        
        # Extract space information if requested
        if include_space_info:
            result['space'] = {
                'id': target_space.id(),
                'GlobalId': target_space.GlobalId,
                'Name': target_space.Name,
                'LongName': target_space.LongName,
                'ObjectType': target_space.ObjectType,
                'Description': target_space.Description
            }
        
        # Find elements of specified types within the space
        elements_found = []
        element_types_with_matches = []
        
        for elem_type in element_types:
            type_elements = ifc_file.by_type(elem_type)
            type_matches = []
            
            for element in type_elements:
                # Check if element is contained in the target space
                container = ifcopenshell.util.element.get_container(element)
                if container and container.id() == target_space.id():
                    element_info = {
                        'id': element.id(),
                        'GlobalId': element.GlobalId,
                        'Name': element.Name,
                        'ObjectType': element.ObjectType,
                        'Type': element.is_a()
                    }
                    
                    # Add properties if requested
                    if include_element_properties:
                        try:
                            if property_sets:
                                # Get specific property sets
                                element_info['properties'] = {}
                                for pset_name in property_sets:
                                    pset = ifcopenshell.util.element.get_pset(element, pset_name)
                                    if pset:
                                        element_info['properties'][pset_name] = pset
                            else:
                                # Get all property sets
                                element_info['properties'] = ifcopenshell.util.element.get_psets(element)
                        except Exception as e:
                            element_info['properties'] = f"Error extracting properties: {str(e)}"
                    
                    type_matches.append(element_info)
            
            if type_matches:
                element_types_with_matches.append(elem_type)
                elements_found.extend(type_matches)
        
        # Update result
        result['elements'] = elements_found
        result['count'] = len(elements_found)
        result['element_types_found'] = element_types_with_matches
        
        return result
        
    except Exception as e:
        # Return error information in structured format
        return {
            'space': {},
            'elements': [],
            'count': 0,
            'element_types_found': [],
            'error': f"Error in get_elements_in_space: {str(e)}"
        }