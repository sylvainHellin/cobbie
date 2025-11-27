import ifcopenshell
import ifcopenshell.util.placement
from typing import List, Dict, Union, Optional
import logging

# Set up logging
logger = logging.getLogger(__name__)

def get_building_levels(
    ifc_file: ifcopenshell.file,
    include_coordinates: bool = True,
    include_global_ids: bool = False,
    sort_by_elevation: bool = True,
    level_patterns: Optional[Dict[str, List[str]]] = None,
    calculate_heights: bool = False,
    height_reference_level: Optional[str] = None
) -> Union[List[Dict[str, Union[str, float, List[float]]]], Dict[str, Union[List, Dict]]]:
    """
    Extracts comprehensive information about building levels (IfcBuildingStorey elements) from an IFC model.
    
    This function retrieves level information including names, elevations, and optionally spatial
    coordinates and global IDs. It handles the common pattern of retrieving level information for
    vertical coordination, floor-based analysis, and spatial queries.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        include_coordinates: Boolean to include placement coordinates (default: True)
        include_global_ids: Boolean to include GlobalId values (default: False)
        sort_by_elevation: Boolean to sort results by elevation (default: True)
        level_patterns: Optional dictionary mapping semantic names to keyword patterns
                       (e.g., {'first_floor': ['first', '1', 'ground', 'eg'], 'second_floor': ['second', '2', 'og']})
        calculate_heights: Boolean to automatically compute floor-to-floor heights between found levels
        height_reference_level: Optional string specifying which level to use as reference for height calculations
    
    Returns:
        If level_patterns is None: List of dictionaries containing level information with keys:
        - 'Name': str - The name of the building storey
        - 'Elevation': float - The elevation value
        - 'Coordinates': List[float] - XYZ coordinates (optional, when include_coordinates=True)
        - 'GlobalId': str - GlobalId value (optional, when include_global_ids=True)
        
        If level_patterns is provided: Dictionary with keys:
        - 'levels': List[Dict] - Same structure as above
        - 'found_levels': Dict[str, Dict] - Mapping of semantic names to level information
        - 'floor_heights': Dict[str, float] - Floor-to-floor heights (when calculate_heights=True)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> levels = get_building_levels(model, include_coordinates=True, include_global_ids=True)
        >>> for level in levels:
        ...     print(f"{level['Name']}: {level['Elevation']}m")
        
        >>> # With level patterns and height calculation
        >>> patterns = {'first_floor': ['first', '1'], 'second_floor': ['second', '2']}
        >>> result = get_building_levels(model, level_patterns=patterns, calculate_heights=True)
        >>> print(result['floor_heights'])
    """
    try:
        # Validate input
        if not isinstance(ifc_file, ifcopenshell.file):
            raise TypeError("ifc_file must be an ifcopenshell.file instance")
        
        # Get all building storey elements
        building_storeys = ifc_file.by_type('IfcBuildingStorey')
        
        if not building_storeys:
            logger.warning("No IfcBuildingStorey elements found in the model")
            return [] if level_patterns is None else {'levels': [], 'found_levels': {}, 'floor_heights': {}}
        
        levels_info = []
        
        for storey in building_storeys:
            level_info = {}
            
            # Extract name - use uppercase key
            level_info['Name'] = getattr(storey, 'Name', 'Unnamed Level')
            
            # Extract elevation - try multiple methods
            elevation = None
            
            # Method 1: Direct Elevation property
            if hasattr(storey, 'Elevation') and storey.Elevation is not None:
                elevation = float(storey.Elevation)
            
            # Method 2: Extract from ObjectPlacement coordinates
            elif (include_coordinates and 
                  hasattr(storey, 'ObjectPlacement') and 
                  storey.ObjectPlacement is not None):
                try:
                    # Use ifcopenshell.util.placement.get_local_placement for robust extraction
                    matrix = ifcopenshell.util.placement.get_local_placement(storey.ObjectPlacement)
                    if matrix is not None:
                        # Extract Z coordinate (elevation) from transformation matrix
                        elevation = float(matrix[2, 3])  # Z coordinate
                except Exception as e:
                    logger.debug(f"Could not extract elevation from placement for {level_info['Name']}: {e}")
                    
                    # Fallback: manual extraction
                    try:
                        placement = storey.ObjectPlacement
                        if (hasattr(placement, 'RelativePlacement') and 
                            placement.RelativePlacement is not None):
                            rel_placement = placement.RelativePlacement
                            if (hasattr(rel_placement, 'Location') and 
                                rel_placement.Location is not None):
                                location = rel_placement.Location
                                if (hasattr(location, 'Coordinates') and 
                                    location.Coordinates is not None and
                                    len(location.Coordinates) >= 3):
                                    elevation = float(location.Coordinates[2])
                    except Exception as e2:
                        logger.debug(f"Fallback placement extraction failed for {level_info['Name']}: {e2}")
            
            # If still no elevation found, use 0.0 as default
            if elevation is None:
                elevation = 0.0
                logger.warning(f"No elevation found for level '{level_info['Name']}', using 0.0")
            
            # Use uppercase key for elevation
            level_info['Elevation'] = elevation
            
            # Extract coordinates if requested - use uppercase key
            if include_coordinates:
                coordinates = None
                try:
                    # Use ifcopenshell.util.placement.get_local_placement for robust extraction
                    matrix = ifcopenshell.util.placement.get_local_placement(storey.ObjectPlacement)
                    if matrix is not None:
                        # Extract XYZ coordinates from transformation matrix
                        coordinates = [
                            float(matrix[0, 3]),  # X coordinate
                            float(matrix[1, 3]),  # Y coordinate
                            float(matrix[2, 3])   # Z coordinate
                        ]
                except Exception as e:
                    logger.debug(f"Could not extract coordinates using placement utility for {level_info['Name']}: {e}")
                    
                    # Fallback: manual extraction
                    try:
                        if (hasattr(storey, 'ObjectPlacement') and 
                            storey.ObjectPlacement is not None):
                            placement = storey.ObjectPlacement
                            if (hasattr(placement, 'RelativePlacement') and 
                                placement.RelativePlacement is not None):
                                rel_placement = placement.RelativePlacement
                                if (hasattr(rel_placement, 'Location') and 
                                    rel_placement.Location is not None):
                                    location = rel_placement.Location
                                    if (hasattr(location, 'Coordinates') and 
                                        location.Coordinates is not None):
                                        coords = location.Coordinates
                                        if len(coords) >= 3:
                                            coordinates = [float(coords[0]), float(coords[1]), float(coords[2])]
                    except Exception as e2:
                        logger.debug(f"Fallback coordinate extraction failed for {level_info['Name']}: {e2}")
                
                # If coordinates extraction failed, use elevation as Z coordinate with 0,0 for X,Y
                if coordinates is None:
                    coordinates = [0.0, 0.0, elevation]
                    logger.warning(f"Using default coordinates for level '{level_info['Name']}': {coordinates}")
                
                # Use uppercase key for coordinates
                level_info['Coordinates'] = coordinates
            
            # Extract global ID if requested - use uppercase key
            if include_global_ids:
                level_info['GlobalId'] = getattr(storey, 'GlobalId', '')
            
            levels_info.append(level_info)
        
        # Sort by elevation if requested
        if sort_by_elevation:
            levels_info.sort(key=lambda x: x['Elevation'])
        
        # If no level patterns provided, return the original format for backward compatibility
        if level_patterns is None:
            return levels_info
        
        # Find levels based on patterns
        found_levels = {}
        for semantic_name, patterns in level_patterns.items():
            for level in levels_info:
                level_name_lower = level['Name'].lower()
                for pattern in patterns:
                    if pattern.lower() in level_name_lower:
                        found_levels[semantic_name] = level
                        break
                if semantic_name in found_levels:
                    break
        
        # Calculate floor-to-floor heights if requested
        floor_heights = {}
        if calculate_heights and found_levels:
            # Determine reference level
            reference_level = None
            if height_reference_level and height_reference_level in found_levels:
                reference_level = found_levels[height_reference_level]
            elif len(found_levels) > 0:
                # Use the first found level as reference
                reference_level = list(found_levels.values())[0]
            
            if reference_level:
                ref_elevation = reference_level['Elevation']
                for semantic_name, level in found_levels.items():
                    if semantic_name != height_reference_level:
                        height = level['Elevation'] - ref_elevation
                        floor_heights[semantic_name] = height
        
        # Return enhanced format
        return {
            'levels': levels_info,
            'found_levels': found_levels,
            'floor_heights': floor_heights
        }
        
    except Exception as e:
        logger.error(f"Error extracting building levels: {e}")
        raise