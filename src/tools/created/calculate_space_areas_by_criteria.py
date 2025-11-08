import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional, Union, Any

def calculate_space_areas_by_criteria(
    ifc_file,
    semantic_keywords: List[str],
    naming_pattern: Optional[Dict[str, str]] = None,
    search_fields: List[str] = ['LongName', 'Name'],
    area_quantity_names: List[str] = ['GrossFloorArea', 'NetFloorArea', 'Area'],
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Calculates total areas of spaces filtered by semantic keywords and naming patterns,
    providing both individual breakdowns and aggregated totals.
    
    This function handles the common BIM analysis pattern of filtering spaces by
    functional keywords (like 'bathroom', 'office', 'storage') and naming conventions
    (like house/unit prefixes, floor identifiers), then extracting area quantities
    and providing comprehensive summaries.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        semantic_keywords: List of keywords to identify target spaces 
                          (e.g., ['bathroom', 'toilet'])
        naming_pattern: Optional dict with 'prefix' or 'suffix' keys for naming filters
                       (e.g., {'prefix': 'A'} for house A)
        search_fields: Fields to search for semantic keywords 
                      (default: ['LongName', 'Name'])
        area_quantity_names: List of area quantity names to search for
                           (default: ['GrossFloorArea', 'NetFloorArea', 'Area'])
        case_sensitive: Whether keyword matching is case sensitive (default: False)
    
    Returns:
        Dict containing:
        - total_area: Sum of all matching space areas
        - space_count: Number of matching spaces
        - spaces: List of individual space details with areas
        - summary: Breakdown by criteria if applicable
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = calculate_space_areas_by_criteria(
        ...     model,
        ...     semantic_keywords=['bathroom'],
        ...     naming_pattern={'prefix': 'A'}
        ... )
        >>> print(f"Total area: {result['total_area']} m²")
    """
    try:
        # Initialize result structure
        result = {
            'total_area': 0.0,
            'space_count': 0,
            'spaces': [],
            'summary': {}
        }
        
        # Get all spaces from the model
        spaces = ifc_file.by_type('IfcSpace')
        
        # Prepare keywords for matching
        if not case_sensitive:
            semantic_keywords = [kw.lower() for kw in semantic_keywords]
        
        matching_spaces = []
        
        # Filter spaces based on criteria
        for space in spaces:
            # Check naming pattern
            name_match = True
            if naming_pattern:
                space_name = getattr(space, 'Name', '')
                if 'prefix' in naming_pattern:
                    if not space_name.startswith(naming_pattern['prefix']):
                        name_match = False
                if 'suffix' in naming_pattern:
                    if not space_name.endswith(naming_pattern['suffix']):
                        name_match = False
            
            if not name_match:
                continue
            
            # Check semantic keywords
            keyword_match = False
            for field in search_fields:
                field_value = getattr(space, field, '')
                if field_value:
                    search_text = field_value if case_sensitive else field_value.lower()
                    for keyword in semantic_keywords:
                        if keyword in search_text:
                            keyword_match = True
                            break
                if keyword_match:
                    break
            
            if not keyword_match:
                continue
            
            # Extract area from quantities
            area = None
            try:
                # Get quantities using ifcopenshell utility
                quantities = ifcopenshell.util.element.get_psets(space, qtos_only=True)
                
                # Search for area quantities
                for qset_name, qset_data in quantities.items():
                    for qty_name, qty_value in qset_data.items():
                        # Check if this is an area quantity we're looking for
                        qty_name_lower = qty_name.lower() if not case_sensitive else qty_name
                        for area_name in area_quantity_names:
                            search_name = area_name.lower() if not case_sensitive else area_name
                            if search_name in qty_name_lower:
                                if isinstance(qty_value, (int, float)) and qty_value > 0:
                                    area = float(qty_value)
                                    break
                        if area is not None:
                            break
                    if area is not None:
                        break
                
                # If no area found in quantities, try direct IsDefinedBy relationship
                if area is None:
                    for rel in space.IsDefinedBy:
                        if hasattr(rel, 'RelatingPropertyDefinition'):
                            prop_def = rel.RelatingPropertyDefinition
                            if hasattr(prop_def, 'Quantities'):
                                for qty in prop_def.Quantities:
                                    if hasattr(qty, 'Name') and hasattr(qty, 'AreaValue'):
                                        qty_name = str(qty.Name)
                                        qty_name_lower = qty_name.lower() if not case_sensitive else qty_name
                                        for area_name in area_quantity_names:
                                            search_name = area_name.lower() if not case_sensitive else area_name
                                            if search_name in qty_name_lower:
                                                area = float(qty.AreaValue)
                                                break
                                        if area is not None:
                                            break
                                if area is not None:
                                    break
                            
            except Exception as e:
                # Continue with area = None if extraction fails
                pass
            
            # Create space detail
            space_detail = {
                'id': getattr(space, 'GlobalId', ''),
                'name': getattr(space, 'Name', ''),
                'long_name': getattr(space, 'LongName', ''),
                'area': area if area is not None else 0.0,
                'has_area': area is not None
            }
            
            matching_spaces.append(space_detail)
        
        # Calculate totals and create summary
        total_area = 0.0
        spaces_with_area = 0
        
        for space_detail in matching_spaces:
            if space_detail['has_area']:
                total_area += space_detail['area']
                spaces_with_area += 1
        
        result['total_area'] = total_area
        result['space_count'] = len(matching_spaces)
        result['spaces'] = matching_spaces
        result['summary'] = {
            'total_spaces_found': len(matching_spaces),
            'spaces_with_area_data': spaces_with_area,
            'spaces_without_area_data': len(matching_spaces) - spaces_with_area,
            'average_area': total_area / spaces_with_area if spaces_with_area > 0 else 0.0
        }
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'total_area': 0.0,
            'space_count': 0,
            'spaces': [],
            'summary': {},
            'error': str(e)
        }