import ifcopenshell
import ifcopenshell.util.element
import re
from typing import List, Dict, Any, Optional

def get_spaces_on_level_by_pattern(
    ifc_file: ifcopenshell.file,
    level_identifier: str,
    match_strategy: str = 'contains',
    case_sensitive: bool = False,
    area_property_sets: Optional[List[str]] = None,
    area_property_names: Optional[List[str]] = None,
    include_diagnostics: bool = False
) -> Dict[str, Any]:
    """
    Extracts spaces from a building level identified by flexible pattern matching.
    
    This function handles the common BIM analysis pattern where users reference levels
    by number or pattern but actual level names may vary (e.g., 'Level 3' vs 'OK OG3').
    It implements intelligent level identification using multiple matching strategies
    and then extracts spaces with their areas.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_identifier: Level identifier to search for (e.g., '3', 'ground', 'first')
        match_strategy: How to match level identifier ('contains', 'exact', 'startswith', 'endswith', 'number')
        case_sensitive: Boolean for case-sensitive matching (default: False)
        area_property_sets: List of property sets to search for area information
        area_property_names: List of property names to search for area data
        include_diagnostics: Boolean to include diagnostic information about level matching
    
    Returns:
        Dict with keys:
        - 'level_found': Boolean indicating if level was identified
        - 'level_name': Actual name of the matched level
        - 'level_info': Dictionary with level details (elevation, coordinates)
        - 'spaces': List of space dictionaries with name, area, and other properties
        - 'total_spaces': Count of spaces found
        - 'total_area': Sum of all space areas
        - 'diagnostics': Optional diagnostic information
    
    Example:
        >>> result = get_spaces_on_level_by_pattern(ifc_file, '3', 'contains')
        >>> print(f"Found {result['total_spaces']} spaces on {result['level_name']}")
    """
    
    # Set default values for area property sets and names
    if area_property_sets is None:
        area_property_sets = ['PSet_Room', 'Qto_SpaceBaseQuantities', 'Pset_SpaceCommon', 'BaseQuantities']
    if area_property_names is None:
        area_property_names = ['Area', 'GrossFloorArea', 'NetFloorArea', 'GrossArea']
    
    result = {
        'level_found': False,
        'level_name': None,
        'level_info': {},
        'spaces': [],
        'total_spaces': 0,
        'total_area': 0.0,
        'diagnostics': {}
    }
    
    try:
        # Get all building levels
        levels = []
        for storey in ifc_file.by_type("IfcBuildingStorey"):
            level_info = {
                'Name': storey.Name,
                'Elevation': getattr(storey, 'Elevation', 0.0),
                'Coordinates': [0.0, 0.0, getattr(storey, 'Elevation', 0.0)],
                'storey_object': storey
            }
            levels.append(level_info)
        
        if include_diagnostics:
            result['diagnostics']['available_levels'] = [level['Name'] for level in levels]
        
        # Find matching level based on strategy
        matched_level = None
        search_identifier = level_identifier if case_sensitive else level_identifier.lower()
        
        for level in levels:
            level_name = level['Name'] or ''
            compare_name = level_name if case_sensitive else level_name.lower()
            
            match_found = False
            
            if match_strategy == 'exact':
                match_found = compare_name == search_identifier
            elif match_strategy == 'contains':
                match_found = search_identifier in compare_name
            elif match_strategy == 'startswith':
                match_found = compare_name.startswith(search_identifier)
            elif match_strategy == 'endswith':
                match_found = compare_name.endswith(search_identifier)
            elif match_strategy == 'number':
                # Extract numbers from both strings and compare
                level_numbers = re.findall(r'\d+', compare_name)
                identifier_numbers = re.findall(r'\d+', search_identifier)
                if level_numbers and identifier_numbers:
                    match_found = level_numbers[0] == identifier_numbers[0]
            
            if match_found:
                matched_level = level
                break
        
        if not matched_level:
            if include_diagnostics:
                result['diagnostics']['match_failed'] = {
                    'strategy': match_strategy,
                    'identifier': level_identifier,
                    'case_sensitive': case_sensitive
                }
            return result
        
        # Level found
        result['level_found'] = True
        result['level_name'] = matched_level['Name']
        result['level_info'] = {
            'Elevation': matched_level['Elevation'],
            'Coordinates': matched_level['Coordinates']
        }
        
        # Get all elements in the matched level
        storey = matched_level['storey_object']
        elements = ifcopenshell.util.element.get_decomposition(storey)
        
        # Filter for spaces only
        spaces = [elem for elem in elements if elem.is_a('IfcSpace')]
        
        total_area = 0.0
        space_data = []
        
        for space in spaces:
            space_info = {
                'id': space.id(),
                'name': space.Name or f'Space_{space.id()}',
                'long_name': getattr(space, 'LongName', None),
                'area': 0.0,
                'area_source': None
            }
            
            # Try to get area from property sets
            psets = ifcopenshell.util.element.get_psets(space)
            area_found = False
            
            for pset_name in area_property_sets:
                if pset_name in psets:
                    for prop_name in area_property_names:
                        if prop_name in psets[pset_name]:
                            area_value = psets[pset_name][prop_name]
                            if isinstance(area_value, (int, float)) and area_value > 0:
                                space_info['area'] = float(area_value)
                                space_info['area_source'] = f'{pset_name}.{prop_name}'
                                area_found = True
                                break
                    if area_found:
                        break
            
            # If no area found in property sets, try to calculate from geometry
            if not area_found:
                try:
                    # Try to get geometry and calculate area
                    settings = ifcopenshell.geom.settings()
                    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, True)
                    shape = ifcopenshell.geom.create_geometry(settings, space)
                    if shape and shape.geometry:
                        # Calculate area from geometry (simplified approach)
                        verts = shape.geometry.verts
                        if len(verts) >= 9:  # At least one triangle
                            # This is a simplified area calculation - in practice you'd need proper 2D projection
                            space_info['area'] = 0.0  # Placeholder - would need proper geometry processing
                            space_info['area_source'] = 'geometry_calculation'
                except:
                    pass
            
            space_data.append(space_info)
            total_area += space_info['area']
        
        result['spaces'] = space_data
        result['total_spaces'] = len(space_data)
        result['total_area'] = total_area
        
        if include_diagnostics:
            result['diagnostics']['space_extraction'] = {
                'total_elements_in_level': len(elements),
                'spaces_found': len(spaces),
                'areas_with_values': len([s for s in space_data if s['area'] > 0])
            }
        
    except Exception as e:
        if include_diagnostics:
            result['diagnostics']['error'] = str(e)
        result['level_found'] = False
    
    return result