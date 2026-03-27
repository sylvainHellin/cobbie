import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.geom
import numpy as np
from shapely.geometry import Polygon
from typing import List, Optional, Tuple
import warnings

warnings.filterwarnings('ignore')

def get_element_2d_polygon(element, settings) -> Optional[Tuple[Polygon, Tuple[float, float]]]:
    """Get 2D convex hull polygon and center for an element."""
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = np.array(shape.geometry.verts).reshape(-1, 3)
        
        placement = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
        verts_world = verts @ placement[:3, :3].T + placement[:3, 3]
        
        # Project to 2D (X-Y plane)
        verts_2d = verts_world[:, :2]
        
        # Create convex hull polygon
        try:
            from scipy.spatial import ConvexHull
            hull = ConvexHull(verts_2d)
            hull_points = verts_2d[hull.vertices]
            polygon = Polygon(hull_points)
            center = (verts_2d.min(axis=0) + verts_2d.max(axis=0)) / 2
            return polygon, center
        except:
            return None, None
    except Exception:
        return None, None

def check_clearance_front_of_doors(path_ifc_model: str) -> List[str]:
    """
    Check clearance in front of doors in the IFC model.
    
    This rule checks there is enough clearance in front of doors.
    Parameters:
    - Width: Door width from model
    - Depth: 1.2 m clearance depth
    - Height Adjustment: 0.05 m
    - Check both sides: false (only front)
    - Exclude: Door is Hatch
    
    Args:
        path_ifc_model: Path to the IFC model file
    
    Returns:
        List of IFC GUIDs of doors that violate the clearance rule
        (i.e., doors that have components intersecting their required clearance area)
    
    Example:
        >>> violations = check_clearance_front_of_doors('model.ifc')
        >>> print(f"Found {len(violations)} doors with clearance violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    clearance_depth = 1.2
    height_adjustment = 0.05
    # Minimum intersection area as percentage of clearance zone
    min_intersection_ratio = 0.10  # 10% of clearance zone area
    
    settings = ifcopenshell.geom.settings()
    doors = model.by_type('IfcDoor')
    
    if not doors:
        return []
    
 # Obstruction types based on ground truth analysis
    obstruction_types = {
        'IfcFlowTerminal', 'IfcCurtainWall', 'IfcFurniture', 
        'IfcFurnishingElement', 'IfcWall', 'IfcWindow'
    }
    
    # Pre-compute 2D polygons for relevant elements
    element_data = []  # (guid, polygon, center, is_door, is_obstruction)
    
    for element in model:
        element_guid = getattr(element, 'GlobalId', None)
        if element_guid is None:
            continue
        
        # Skip non-product elements
        skip_types = ['IfcOpeningElement', 'IfcSpace', 'IfcVirtualElement',
                      'IfcGrid', 'IfcGridAxis', 'IfcAnnotation',
                      'IfcSite', 'IfcBuilding', 'IfcBuildingStorey',
                      'IfcProject', 'IfcDoorType', 'IfcWindowType',
                      'IfcElementType', 'IfcTypeProduct', 'IfcBeam',
                      'IfcColumn', 'IfcSlab', 'IfcStair', 'IfcRailing']
        if element.is_a() in skip_types:
            continue
        
        is_door = element.is_a('IfcDoor')
        is_obstruction = any(element.is_a(t) for t in obstruction_types)
        
        # Store doors and obstructions
        if is_door or is_obstruction:
            polygon, center = get_element_2d_polygon(element, settings)
            if polygon is not None and not polygon.is_empty:
                element_data.append((element_guid, polygon, center, is_door, is_obstruction))
    
    violation_doors = []
    
    for door in doors:
        door_guid = getattr(door, 'GlobalId', None)
        if door_guid is None:
            continue
        
        try:
            # Check if door is a hatch (exclude)
            door_type = ifcopenshell.util.element.get_type(door)
            if door_type:
                type_name = getattr(door_type, 'Name', '').lower()
                if 'hatch' in type_name:
                    continue
            
            placement = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
            
            # Get door's front direction (Y-axis in local coords)
            front_dir = placement[:2, 1]  # 2D front direction
            door_position = placement[:2, 3]  # 2D position
            
            psets = ifcopenshell.util.element.get_psets(door)
            qto = psets.get('Qto_DoorBaseQuantities', {})
            
            door_width = qto.get('Width', 0.9)
            door_height = qto.get('Height', 2.1)
            
            # Create clearance zone polygon in local coords (2D)
            c_corners_local = np.array([
                [-door_width/2, 0],
                [door_width/2, 0],
                [door_width/2, clearance_depth],
                [-door_width/2, clearance_depth],
            ])
            
            # Transform to world coords (2D)
            rotation = placement[:2, :2]
            translation = placement[:2, 3]
            c_corners_world = c_corners_local @ rotation.T + translation
            clearance_poly = Polygon(c_corners_world)
            
            if clearance_poly.is_empty:
                continue
            
            clearance_area = clearance_poly.area
            c_bounds = clearance_poly.bounds
            c_center = (c_corners_world.min(axis=0) + c_corners_world.max(axis=0)) / 2
            
            has_violation = False
            
            for obs_guid, obs_poly, obs_center, obs_is_door, obs_is_obstruction in element_data:
                if obs_guid == door_guid:
                    continue
                
                # Quick distance check
                dist = np.linalg.norm(obs_center - c_center)
                if dist > clearance_depth + 2.0:
                    continue
                
                # Quick bounds check
                obs_bounds = obs_poly.bounds
                if not np.all((obs_bounds[2:] >= c_bounds[:2]) & (obs_bounds[:2] <= c_bounds[2:])):
                    continue
                
                # Check if obstruction is actually IN FRONT of the door
                # Vector from door position to obstruction center
                door_to_obs = obs_center - door_position
                # Project onto front direction
                front_projection = np.dot(door_to_obs, front_dir)
                
                # Obstruction must be in front (positive projection)
                if front_projection < 0.1:  # Small threshold to handle edge cases
                    continue
                
                # Precise intersection check
                if clearance_poly.intersects(obs_poly):
                    intersection = clearance_poly.intersection(obs_poly)
                    
                    # Different thresholds for door-to-door vs door-to-obstruction
                    if obs_is_door:
                        # Door-to-door: need more significant overlap
                        min_ratio = 0.20  # 20% of clearance zone
                    else:
                        # Door-to-obstruction: need significant overlap
                        min_ratio = min_intersection_ratio
                    
                    if intersection.area > clearance_area * min_ratio:
                        has_violation = True
                        break
            
            if has_violation:
                violation_doors.append(door_guid)
            
        except Exception:
            continue
    
    return sorted(violation_doors)