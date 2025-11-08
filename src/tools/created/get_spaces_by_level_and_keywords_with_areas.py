import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def get_spaces_by_level_and_keywords_with_areas(
    ifc_file: ifcopenshell.file,
    level_name: str,
    keywords: List[str],
    search_fields: List[str] = ['LongName', 'Name'],
    area_sources: List[str] = ['PSet_Room', 'BaseQuantities'],
    area_property_names: List[str] = ['Area', 'GrossFloorArea', 'NetFloorArea'],
    case_sensitive: bool = False,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Extracts spaces from a specific building level that match semantic keywords, with comprehensive area extraction.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_name: Name of the building level to search (e.g., 'OK OG2', 'Ground Floor')
        keywords: List of keywords to identify target spaces (e.g., ['toilet', 'wc', 'restroom'])
        search_fields: Fields to search for keywords (default: ['LongName', 'Name'])
        area_sources: List of property sets to search for area information (default: ['PSet_Room', 'BaseQuantities'])
        area_property_names: List of property names for area (default: ['Area', 'GrossFloorArea', 'NetFloorArea'])
        case_sensitive: Whether keyword matching is case sensitive (default: False)
        include_details: Whether to include full space details (default: True)
    
    Returns:
        Dict containing:
        - level: The level name that was searched
        - total_spaces_found: Count of spaces matching keywords on the level
        - spaces: List of space dictionaries with name, area, and details
        - total_area: Sum of all space areas
        - area_sources_found: Which property sets contained area information
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = get_spaces_by_level_and_keywords_with_areas(
        ...     ifc_file=model,
        ...     level_name='OK OG2',
        ...     keywords=['toilet', 'wc', 'restroom']
        ... )
        >>> print(f"Found {result['total_spaces_found']} restroom spaces")
        >>> print(f"Total area: {result['total_area']} m²")
    """
    try:
        # Initialize result structure
        result = {
            'level': level_name,
            'total_spaces_found': 0,
            'spaces': [],
            'total_area': 0.0,
            'area_sources_found': set()
        }
        
        # Helper function to get the building storey for a space
        def get_space_building_storey(space):
            """Get the building storey that contains this space using Decomposes relationship"""
            if hasattr(space, 'Decomposes') and space.Decomposes:
                for rel in space.Decomposes:
                    if hasattr(rel, 'RelatingObject'):
                        relating_obj = rel.RelatingObject
                        if relating_obj.is_a('IfcBuildingStorey'):
                            return relating_obj
            return None
        
        # Get all spaces in the model
        all_spaces = ifc_file.by_type('IfcSpace')
        
        # Process each space
        for space in all_spaces:
            # Check if space is on the specified level using Decomposes relationship
            building_storey = get_space_building_storey(space)
            if not building_storey or building_storey.Name != level_name:
                continue
            
            # Check if space matches keywords
            space_matches = False
            space_data = {
                'id': space.id(),
                'name': getattr(space, 'Name', ''),
                'long_name': getattr(space, 'LongName', ''),
                'area': None,
                'area_source': None
            }
            
            # Search for keywords in specified fields
            for field in search_fields:
                field_value = getattr(space, field, '')
                if field_value:
                    search_value = field_value if case_sensitive else field_value.lower()
                    for keyword in keywords:
                        search_keyword = keyword if case_sensitive else keyword.lower()
                        if search_keyword in search_value:
                            space_matches = True
                            break
                if space_matches:
                    break
            
            if not space_matches:
                continue
            
            # Extract area information from multiple sources
            psets = ifcopenshell.util.element.get_psets(space)
            
            for area_source in area_sources:
                if area_source in psets:
                    for area_prop in area_property_names:
                        if area_prop in psets[area_source]:
                            space_data['area'] = psets[area_source][area_prop]
                            space_data['area_source'] = f"{area_source}.{area_prop}"
                            result['area_sources_found'].add(area_source)
                            break
                    if space_data['area'] is not None:
                        break
                if space_data['area'] is not None:
                    break
            
            # Add additional details if requested
            if include_details:
                space_data['properties'] = psets
                space_data['global_id'] = getattr(space, 'GlobalId', '')
                space_data['object_type'] = getattr(space, 'ObjectType', '')
            
            # Add to results
            result['spaces'].append(space_data)
            if space_data['area'] is not None:
                result['total_area'] += float(space_data['area'])
        
        # Update counts
        result['total_spaces_found'] = len(result['spaces'])
        result['area_sources_found'] = list(result['area_sources_found'])
        
        return result
        
    except Exception as e:
        return {
            'level': level_name,
            'total_spaces_found': 0,
            'spaces': [],
            'total_area': 0.0,
            'area_sources_found': [],
            'error': str(e)
        }