import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
from typing import List, Dict, Tuple, Optional, Any

def calculate_floor_to_floor_heights(
    ifc_file: ifcopenshell.file,
    floor_identifiers: Optional[Dict[str, List[str]]] = None,
    calculate_all_consecutive: bool = False,
    specific_floors: Optional[List[Tuple[str, str]]] = None,
    case_sensitive: bool = False,
    include_level_details: bool = True
) -> Dict[str, Any]:
    """
    Calculates floor-to-floor heights between building levels with flexible floor identification.
    
    This function handles the common BIM analysis task of determining vertical distances 
    between floors by combining level extraction, intelligent floor identification, and 
    elevation calculations. It supports various naming conventions and can calculate heights 
    between consecutive floors or specific floor pairs.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        floor_identifiers: Dict mapping floor types to name patterns 
            (e.g., {'ground': ['ground', '0', 'eg'], 'first': ['first', '1', 'og']})
        calculate_all_consecutive: Boolean to calculate heights between all consecutive floors
        specific_floors: List of floor pairs to calculate heights between 
            (e.g., [('ground', 'first')])
        case_sensitive: Boolean for name matching
        include_level_details: Boolean to include full level information in results
    
    Returns:
        Dict containing:
        - 'floor_heights': List of height calculations with floor names and height values
        - 'levels': Full level information (if include_level_details=True)
        - 'unidentified_floors': List of floor identifiers that couldn't be matched
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = calculate_floor_to_floor_heights(
        ...     model,
        ...     floor_identifiers={'ground': ['ground', '0', 'eg'], 'first': ['first', '1', 'og']},
        ...     specific_floors=[('ground', 'first')]
        ... )
        >>> print(result['floor_heights'])
        [{'from_floor': 'Level 1', 'to_floor': 'Level 2', 'height': 3.1}]
    """
    
    try:
        # Extract building levels
        storeys = ifc_file.by_type('IfcBuildingStorey')
        levels_data = []
        
        for storey in storeys:
            # Get elevation from attribute or placement
            elevation = storey.Elevation
            
            # Get placement coordinates as fallback
            if storey.ObjectPlacement and elevation is None:
                matrix = ifcopenshell.util.placement.get_local_placement(storey.ObjectPlacement)
                coordinates = matrix[:,3][:3]
                elevation = coordinates[2]
            elif elevation is None:
                elevation = 0.0
            
            level_data = {
                'Name': storey.Name or '',
                'Elevation': float(elevation),
                'Coordinates': [0.0, 0.0, float(elevation)]
            }
            levels_data.append(level_data)
        
        # Sort levels by elevation
        levels_data.sort(key=lambda x: x['Elevation'])
        
        # Initialize results
        floor_heights = []
        unidentified_floors = []
        
        # Default floor identifiers if not provided
        if floor_identifiers is None:
            floor_identifiers = {
                'ground': ['ground', '0', 'eg'],
                'first': ['first', '1', 'og'],
                'second': ['second', '2', 'dg'],
                'basement': ['basement', 'b', 't/fdn', 'foundation'],
                'roof': ['roof']
            }
        
        # Create mapping from floor identifiers to actual level names
        floor_mapping = {}
        used_levels = set()  # Track levels that have been matched to avoid conflicts
        
        for floor_type, patterns in floor_identifiers.items():
            matched_level = None
            for level in levels_data:
                if level['Name'] in used_levels:
                    continue  # Skip levels already matched to avoid conflicts
                    
                level_name = level['Name']
                if not case_sensitive:
                    level_name_lower = level_name.lower()
                    for pattern in patterns:
                        if pattern.lower() in level_name_lower:
                            matched_level = level
                            break
                else:
                    for pattern in patterns:
                        if pattern in level_name:
                            matched_level = level
                            break
                
                if matched_level:
                    used_levels.add(matched_level['Name'])
                    break
            
            if matched_level:
                floor_mapping[floor_type] = matched_level
            else:
                unidentified_floors.append(floor_type)
        
        # Calculate heights for specific floor pairs
        if specific_floors:
            for from_floor, to_floor in specific_floors:
                if from_floor in floor_mapping and to_floor in floor_mapping:
                    from_level = floor_mapping[from_floor]
                    to_level = floor_mapping[to_floor]
                    height = to_level['Elevation'] - from_level['Elevation']
                    
                    floor_heights.append({
                        'from_floor_type': from_floor,
                        'to_floor_type': to_floor,
                        'from_floor': from_level['Name'],
                        'to_floor': to_level['Name'],
                        'height': round(height, 6),
                        'from_elevation': from_level['Elevation'],
                        'to_elevation': to_level['Elevation']
                    })
                else:
                    if from_floor not in floor_mapping:
                        unidentified_floors.append(from_floor)
                    if to_floor not in floor_mapping:
                        unidentified_floors.append(to_floor)
        
        # Calculate heights for all consecutive floors
        if calculate_all_consecutive:
            for i in range(len(levels_data) - 1):
                from_level = levels_data[i]
                to_level = levels_data[i + 1]
                height = to_level['Elevation'] - from_level['Elevation']
                
                floor_heights.append({
                    'from_floor_type': None,
                    'to_floor_type': None,
                    'from_floor': from_level['Name'],
                    'to_floor': to_level['Name'],
                    'height': round(height, 6),
                    'from_elevation': from_level['Elevation'],
                    'to_elevation': to_level['Elevation']
                })
        
        # Prepare result
        result = {
            'floor_heights': floor_heights,
            'unidentified_floors': list(set(unidentified_floors))  # Remove duplicates
        }
        
        if include_level_details:
            result['levels'] = levels_data
        
        return result
        
    except Exception as e:
        return {
            'floor_heights': [],
            'unidentified_floors': list(floor_identifiers.keys()) if floor_identifiers else [],
            'error': str(e)
        }