import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_spaces_by_keywords_and_level(
    ifc_file,
    keywords: List[str],
    search_fields: List[str] = ['name', 'long_name'],
    include_areas: bool = True,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes spaces across all building levels, filtering by semantic keywords and providing area/count summaries by level.
    
    This function answers questions like 'how many X spaces are on each floor and what are their areas?' 
    by combining level iteration, keyword-based space identification, and area calculation.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        keywords: List of keywords to identify target spaces (e.g., ['toilet', 'wc', 'restroom'])
        search_fields: Fields to search for keywords (default: ['name', 'long_name'])
        include_areas: Whether to calculate and include area information (default: True)
        case_sensitive: Whether keyword matching should be case sensitive (default: False)
    
    Returns:
        Dict containing:
        - levels: List of level information with matching spaces
        - summary: Overall counts and totals
        - details: Full list of matching spaces with their properties
        
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_spaces_by_keywords_and_level(
        ...     model, 
        ...     keywords=['wc', 'toilet', 'restroom'],
        ...     include_areas=True
        ... )
        >>> print(f"Total restrooms: {result['summary']['total_count']}")
        >>> for level in result['levels']:
        ...     if level['count'] > 0:
        ...         print(f"{level['level_name']}: {level['count']} restrooms")
    """
    try:
        # Get all building storeys sorted by elevation
        storeys = ifc_file.by_type('IfcBuildingStorey')
        storeys_sorted = sorted(storeys, key=lambda s: float(s.Elevation) if s.Elevation else 0)
        
        # Get all spaces
        spaces = ifc_file.by_type('IfcSpace')
        
        # Prepare keywords for matching
        if not case_sensitive:
            keywords = [kw.lower() for kw in keywords]
        
        # Build level data structure
        levels_data = []
        all_matching_spaces = []
        total_count = 0
        total_area = 0.0
        
        for storey in storeys_sorted:
            level_name = storey.Name or f"Level_{storey.id}"
            elevation = float(storey.Elevation) if storey.Elevation else 0
            
            # Get spaces on this storey using decomposition
            storey_spaces = ifcopenshell.util.element.get_decomposition(storey)
            
            # Filter for IfcSpace elements
            level_spaces = [s for s in storey_spaces if s.is_a('IfcSpace')]
            
            # Find matching spaces
            matching_spaces = []
            
            for space in level_spaces:
                # Get space properties
                space_data = {
                    'id': space.id,
                    'name': space.Name or '',
                    'long_name': space.LongName or '',
                    'number': getattr(space, 'Name', '') or str(space.id)
                }
                
                # Get area if requested
                if include_areas:
                    psets = ifcopenshell.util.element.get_psets(space)
                    area = 0.0
                    if 'Qto_SpaceBaseQuantities' in psets:
                        area = psets['Qto_SpaceBaseQuantities'].get('NetFloorArea', 0)
                        if isinstance(area, (int, float)):
                            area = float(area)
                        elif isinstance(area, str):
                            try:
                                area = float(area)
                            except:
                                area = 0.0
                    space_data['area'] = area
                
                # Check for keyword matches
                is_match = False
                for field in search_fields:
                    field_value = space_data.get(field, '')
                    if not case_sensitive:
                        field_value = field_value.lower()
                    
                    for keyword in keywords:
                        if keyword in field_value:
                            is_match = True
                            break
                    if is_match:
                        break
                
                if is_match:
                    matching_spaces.append(space_data)
                    all_matching_spaces.append({**space_data, 'level': level_name, 'elevation': elevation})
            
            # Calculate level statistics
            level_count = len(matching_spaces)
            level_total_area = sum(s.get('area', 0) for s in matching_spaces) if include_areas else 0
            
            total_count += level_count
            total_area += level_total_area
            
            levels_data.append({
                'level_name': level_name,
                'elevation': elevation,
                'count': level_count,
                'total_area': level_total_area,
                'spaces': matching_spaces
            })
        
        # Build result
        result = {
            'levels': levels_data,
            'summary': {
                'total_count': total_count,
                'total_area': total_area,
                'levels_with_matches': len([l for l in levels_data if l['count'] > 0])
            },
            'details': all_matching_spaces
        }
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'levels': [],
            'summary': {'total_count': 0, 'total_area': 0, 'levels_with_matches': 0},
            'details': []
        }