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
    sort_by_elevation: bool = True
) -> List[Dict[str, Union[str, float, List[float]]]]:
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
    
    Returns:
        List of dictionaries containing level information with keys:
        - 'name': str - The name of the building storey
        - 'elevation': float - The elevation value
        - 'coordinates': List[float] - XYZ coordinates (optional, when include_coordinates=True)
        - 'global_id': str - GlobalId value (optional, when include_global_ids=True)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> levels = get_building_levels(model, include_coordinates=True, include_global_ids=True)
        >>> for level in levels:
        ...     print(f"{level['name']}: {level['elevation']}m")
    """
    try:
        # Validate input
        if not isinstance(ifc_file, ifcopenshell.file):
            raise TypeError("ifc_file must be an ifcopenshell.file instance")
        
        # Get all building storey elements
        building_storeys = ifc_file.by_type('IfcBuildingStorey')
        
        if not building_storeys:
            logger.warning("No IfcBuildingStorey elements found in the model")
            return []
        
        levels_info = []
        
        for storey in building_storeys:
            level_info = {}
            
            # Extract name
            level_info['name'] = getattr(storey, 'Name', 'Unnamed Level')
            
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
                    logger.debug(f"Could not extract elevation from placement for {level_info['name']}: {e}")
                    
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
                        logger.debug(f"Fallback placement extraction failed for {level_info['name']}: {e2}")
            
            # If still no elevation found, use 0.0 as default
            if elevation is None:
                elevation = 0.0
                logger.warning(f"No elevation found for level '{level_info['name']}', using 0.0")
            
            level_info['elevation'] = elevation
            
            # Extract coordinates if requested
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
                    logger.debug(f"Could not extract coordinates using placement utility for {level_info['name']}: {e}")
                    
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
                        logger.debug(f"Fallback coordinate extraction failed for {level_info['name']}: {e2}")
                
                # If coordinates extraction failed, use elevation as Z coordinate with 0,0 for X,Y
                if coordinates is None:
                    coordinates = [0.0, 0.0, elevation]
                    logger.warning(f"Using default coordinates for level '{level_info['name']}': {coordinates}")
                
                level_info['coordinates'] = coordinates
            
            # Extract global ID if requested
            if include_global_ids:
                level_info['global_id'] = getattr(storey, 'GlobalId', '')
            
            levels_info.append(level_info)
        
        # Sort by elevation if requested
        if sort_by_elevation:
            levels_info.sort(key=lambda x: x['elevation'])
        
        return levels_info
        
    except Exception as e:
        logger.error(f"Error extracting building levels: {e}")
        raise