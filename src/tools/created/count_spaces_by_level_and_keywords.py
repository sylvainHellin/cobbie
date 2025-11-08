import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any

def count_spaces_by_level_and_keywords(
    ifc_file,
    level_name: str,
    keywords: List[str],
    search_fields: List[str] = ['name', 'long_name'],
    case_sensitive: bool = False,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Counts spaces on a specific building level that match semantic keywords.
    
    This function combines level-based space retrieval with keyword filtering to answer
    questions like 'how many toilets on ground floor?' or 'count offices on second floor'.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_name: Name of the building level to search (e.g., 'Erdgeschoss', 'Ground Floor')
        keywords: List of keywords to identify target spaces (e.g., ['toilet', 'wc', 'restroom'])
        search_fields: Fields to search for keywords (default: ['name', 'long_name'])
        case_sensitive: Whether keyword matching should be case sensitive (default: False)
        include_details: Whether to return matching space details (default: True)
    
    Returns:
        Dict containing:
        - count: Number of matching spaces
        - spaces: List of matching space details (if include_details=True)
        - level_name: The level that was searched
        - keywords: The keywords that were used
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = count_spaces_by_level_and_keywords(
        ...     model, 
        ...     level_name='Erdgeschoss',
        ...     keywords=['wc', 'toilet']
        ... )
        >>> print(f"Found {result['count']} toilets on ground floor")
    """
    try:
        # Initialize result
        result = {
            'count': 0,
            'spaces': [],
            'level_name': level_name,
            'keywords': keywords.copy()
        }
        
        # Get all spaces in the model
        all_spaces = ifc_file.by_type('IfcSpace')
        
        # Filter spaces by level and keywords
        matching_spaces = []
        
        for space in all_spaces:
            # Check if space is on the target level using property sets
            space_level = None
            try:
                psets = ifcopenshell.util.element.get_psets(space)
                # Look for level information in ArchiCADProperties
                if 'ArchiCADProperties' in psets:
                    space_level = psets['ArchiCADProperties'].get('Ursprungsgeschoss')
                # Fallback to container relationship if property set doesn't have level
                if not space_level:
                    container = ifcopenshell.util.element.get_container(space)
                    if container:
                        space_level = container.Name
            except:
                # Fallback to container relationship
                container = ifcopenshell.util.element.get_container(space)
                if container:
                    space_level = container.Name
            
            # Check if space matches the target level
            if not space_level or space_level != level_name:
                continue
            
            # Check if space matches keywords
            space_matches = False
            space_info = {
                'id': space.id(),
                'name': getattr(space, 'Name', None) or '',
                'long_name': getattr(space, 'LongName', None) or '',
                'area': 0.0
            }
            
            # Get area from quantities if available
            try:
                psets = ifcopenshell.util.element.get_psets(space, qtos_only=True)
                for qto_name, qto_data in psets.items():
                    if 'FloorArea' in qto_data:
                        space_info['area'] = float(qto_data['FloorArea'])
                        break
                    elif 'GrossFloorArea' in qto_data:
                        space_info['area'] = float(qto_data['GrossFloorArea'])
                        break
            except:
                pass
            
            # Also try to get area from ArchiCAD properties
            try:
                psets = ifcopenshell.util.element.get_psets(space)
                if 'AC_Pset_Raumstempel_01' in psets:
                    grundflache = psets['AC_Pset_Raumstempel_01'].get('Grundfläche')
                    if grundflache:
                        space_info['area'] = float(grundflache)
            except:
                pass
            
            # Search for keywords in specified fields
            for field in search_fields:
                field_value = space_info.get(field, '')
                if field_value:
                    search_text = field_value if case_sensitive else field_value.lower()
                    for keyword in keywords:
                        search_keyword = keyword if case_sensitive else keyword.lower()
                        if search_keyword in search_text:
                            space_matches = True
                            break
                if space_matches:
                    break
            
            if space_matches:
                matching_spaces.append(space_info)
        
        # Update result
        result['count'] = len(matching_spaces)
        if include_details:
            result['spaces'] = matching_spaces
        
        return result
        
    except Exception as e:
        # Return error result
        return {
            'count': 0,
            'spaces': [],
            'level_name': level_name,
            'keywords': keywords.copy(),
            'error': str(e)
        }