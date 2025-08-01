import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *

def estimate_spatial_distances(start_space: str, end_space: str, model_path: str) -> Dict[str, Any]:
    """
    Estimate spatial distances between two spaces in an IFC model.
    
    This function estimates distances based on spatial relationships and geometric properties
    of spaces in a BIM model. It calculates:
    - Direct 3D distance between space centroids
    - Horizontal distance (ignoring Z-axis differences)
    - Vertical distance (Z-axis difference only)
    
    Args:
        start_space (str): Name or GlobalId of the starting space
        end_space (str): Name or GlobalId of the ending space
        model_path (str): Path to the IFC model file
        
    Returns:
        Dict[str, Any]: A dictionary containing:
            - direct_distance: Direct 3D distance between space centroids
            - horizontal_distance: Horizontal distance between spaces
            - vertical_distance: Vertical distance between spaces
            - start_space_info: Information about the start space
            - end_space_info: Information about the end space
            
    Note:
        This function provides estimations based on space centroids and bounding boxes.
        For precise measurements, specialized 3D analysis software should be used.
    """
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all spaces in the model
    spaces = model.by_type("IfcSpace")
    
    # Find the start and end spaces by name or GlobalId
    start_space_obj = None
    end_space_obj = None
    
    for space in spaces:
        # Match by Name or GlobalId
        if space.Name == start_space or space.GlobalId == start_space:
            start_space_obj = space
        if space.Name == end_space or space.GlobalId == end_space:
            end_space_obj = space
    
    if not start_space_obj:
        raise ValueError(f"Start space '{start_space}' not found in the model")
    
    if not end_space_obj:
        raise ValueError(f"End space '{end_space}' not found in the model")
    
    # Extract bounding box information for both spaces
    def get_space_bounding_box(space):
        """Extract bounding box information for a space"""
        if not hasattr(space, 'Representation') or not space.Representation:
            return None
        
        try:
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
            shape = ifcopenshell.geom.create_shape(settings, space)
            
            if shape:
                geometry = shape.geometry
                vertices = geometry.verts
                
                if vertices:
                    # Convert to list of coordinates
                    coords = []
                    for i in range(0, len(vertices), 3):
                        coords.append((vertices[i], vertices[i+1], vertices[i+2]))
                    
                    # Calculate min and max coordinates
                    if coords:
                        min_x = min(coord[0] for coord in coords)
                        max_x = max(coord[0] for coord in coords)
                        min_y = min(coord[1] for coord in coords)
                        max_y = max(coord[1] for coord in coords)
                        min_z = min(coord[2] for coord in coords)
                        max_z = max(coord[2] for coord in coords)
                        
                        return {
                            'min_x': min_x,
                            'max_x': max_x,
                            'min_y': min_y,
                            'max_y': max_y,
                            'min_z': min_z,
                            'max_z': max_z,
                            'centroid': (
                                (min_x + max_x) / 2,
                                (min_y + max_y) / 2,
                                (min_z + max_z) / 2
                            )
                        }
        except Exception as e:
            print(f"Warning: Error processing space {space.GlobalId}: {e}")
            return None
        return None
    
    # Get bounding box information for both spaces
    start_bbox = get_space_bounding_box(start_space_obj)
    end_bbox = get_space_bounding_box(end_space_obj)
    
    if not start_bbox:
        raise ValueError(f"Could not extract bounding box information for start space '{start_space}'")
    
    if not end_bbox:
        raise ValueError(f"Could not extract bounding box information for end space '{end_space}'")
    
    # Calculate distances between centroids
    start_centroid = start_bbox['centroid']
    end_centroid = end_bbox['centroid']
    
    # Direct 3D distance
    direct_distance = math.sqrt(
        (end_centroid[0] - start_centroid[0])**2 +
        (end_centroid[1] - start_centroid[1])**2 +
        (end_centroid[2] - start_centroid[2])**2
    )
    
    # Horizontal distance (ignoring Z-axis)
    horizontal_distance = math.sqrt(
        (end_centroid[0] - start_centroid[0])**2 +
        (end_centroid[1] - start_centroid[1])**2
    )
    
    # Vertical distance (Z-axis difference only)
    vertical_distance = abs(end_centroid[2] - start_centroid[2])
    
    # Prepare result information
    result = {
        "direct_distance": round(direct_distance, 2),
        "horizontal_distance": round(horizontal_distance, 2),
        "vertical_distance": round(vertical_distance, 2),
        "start_space_info": {
            "name": start_space_obj.Name,
            "global_id": start_space_obj.GlobalId,
            "centroid": {
                "x": round(start_centroid[0], 2),
                "y": round(start_centroid[1], 2),
                "z": round(start_centroid[2], 2)
            }
        },
        "end_space_info": {
            "name": end_space_obj.Name,
            "global_id": end_space_obj.GlobalId,
            "centroid": {
                "x": round(end_centroid[0], 2),
                "y": round(end_centroid[1], 2),
                "z": round(end_centroid[2], 2)
            }
        }
    }
    
    return result