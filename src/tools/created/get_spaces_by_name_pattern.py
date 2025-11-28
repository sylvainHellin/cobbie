import ifcopenshell
import ifcopenshell.util.element
import re
from typing import List, Dict, Optional, Union, Any

def get_spaces_by_name_pattern(
    ifc_file: ifcopenshell.file,
    name_pattern: str,
    pattern_type: str = 'startswith',
    case_sensitive: bool = False,
    include_details: bool = True,
    include_properties: bool = False,
    property_sets: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Extracts and counts IFC spaces based on naming patterns, supporting prefix/suffix matching and flexible filtering.
    This function handles the common BIM pattern where spatial organization is encoded in element names
    (e.g., 'A101' for building A, 'B203' for building B, 'Phase1_Room1' for phase-based organization).
    It provides both detailed space information and aggregated counts, making it ideal for questions like
    'how many rooms in house A?' or 'what spaces belong to phase 1?'.

    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        name_pattern: String pattern to match (supports 'startswith', 'endswith', 'contains', 'regex')
        pattern_type: Type of pattern matching ('startswith', 'endswith', 'contains', 'regex')
        case_sensitive: Boolean for case sensitivity (default: False)
        include_details: Boolean to include detailed space information (default: True)
        include_properties: Boolean to extract space properties (default: False)
        property_sets: Optional list of property sets to extract

    Returns:
        Dict containing:
        - total_spaces: Total matching spaces
        - space_names: List of matching space names
        - space_details: List of detailed space information (if include_details=True)
        - pattern_used: The pattern that was matched
        - summary: Brief description of results
    """
    try:
        # Validate inputs
        if not isinstance(ifc_file, ifcopenshell.file):
            raise ValueError("ifc_file must be a valid ifcopenshell.file object")
        
        if not isinstance(name_pattern, str) or not name_pattern:
            raise ValueError("name_pattern must be a non-empty string")
        
        valid_pattern_types = ['startswith', 'endswith', 'contains', 'regex']
        if pattern_type not in valid_pattern_types:
            raise ValueError(f"pattern_type must be one of {valid_pattern_types}")
        
        # Get all spaces in the model
        spaces = ifc_file.by_type('IfcSpace')
        
        # Prepare pattern for matching
        if not case_sensitive:
            pattern_to_match = name_pattern.lower()
        else:
            pattern_to_match = name_pattern
        
        # Compile regex if needed
        if pattern_type == 'regex':
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                regex_pattern = re.compile(name_pattern, flags)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        
        # Filter spaces based on pattern
        matching_spaces = []
        space_names = []
        
        for space in spaces:
            if not space.Name:
                continue
            
            space_name = space.Name
            name_to_check = space_name.lower() if not case_sensitive else space_name
            
            # Apply pattern matching
            is_match = False
            if pattern_type == 'startswith':
                is_match = name_to_check.startswith(pattern_to_match)
            elif pattern_type == 'endswith':
                is_match = name_to_check.endswith(pattern_to_match)
            elif pattern_type == 'contains':
                is_match = pattern_to_match in name_to_check
            elif pattern_type == 'regex':
                is_match = bool(regex_pattern.search(space_name))
            
            if is_match:
                matching_spaces.append(space)
                space_names.append(space_name)
        
        # Prepare space details if requested
        space_details = []
        if include_details and matching_spaces:
            for space in matching_spaces:
                detail = {
                    'id': space.id(),
                    'GlobalId': space.GlobalId,
                    'Name': space.Name,
                    'LongName': space.LongName,
                    'ObjectType': space.ObjectType
                }
                
                # Add properties if requested
                if include_properties:
                    try:
                        if property_sets:
                            # Get specific property sets
                            detail['properties'] = {}
                            for pset_name in property_sets:
                                pset = ifcopenshell.util.element.get_pset(space, pset_name)
                                if pset:
                                    detail['properties'][pset_name] = pset
                        else:
                            # Get all property sets
                            detail['properties'] = ifcopenshell.util.element.get_psets(space)
                    except Exception as e:
                        detail['properties_error'] = str(e)
                
                space_details.append(detail)
        
        # Prepare result
        result = {
            'total_spaces': len(matching_spaces),
            'space_names': space_names,
            'pattern_used': f"{pattern_type}: '{name_pattern}'",
            'summary': f"Found {len(matching_spaces)} spaces matching {pattern_type} pattern '{name_pattern}'"
        }
        
        if include_details:
            result['space_details'] = space_details
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'total_spaces': 0,
            'space_names': [],
            'pattern_used': f"{pattern_type}: '{name_pattern}'",
            'summary': f"Error occurred: {str(e)}"
        }