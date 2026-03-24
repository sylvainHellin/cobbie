import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.geom
import numpy as np
import multiprocessing
from typing import List, Tuple, Optional


def check_clearance_front_of_doors(path_ifc_model: str) -> List[str]:
    """
    Check clearance in front of doors and return GUIDs of doors that have violations.
    
    This rule checks there is enough clearance in front of doors by detecting
    components that intersect the required free area.
    
    Parameters:
        Width Adjustment: 0.05 m
        Depth: 0.8 m
        Height: 2.1 m
        Check both sides: false
        Exclude: Door is Hatch
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of doors that violate the clearance rule
        (i.e., doors that have components intersecting their clearance zones)
        
    Example:
        >>> violations = check_clearance_front_of_doors('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} doors with clearance issues")
        ['2BBCNtipfAzRdC1d8kaceQ', '3AUzwv4Jf2cxVtECK5ADvs', ...]
    """
    # Clearance parameters
    WIDTH_ADJUSTMENT = 0.05
    CLEARANCE_DEPTH = 0.8
    DOOR_HEIGHT = 2.1
    
    # Open the model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all doors
    doors = model.by_type('IfcDoor')
    if not doors:
        return []
    
    # Initialize geometry settings
    settings = ifcopenshell.geom.settings()
    
    def get_door_width(door) -> Optional[float]:
        """Get door width from properties or geometry."""
        try:
            psets = ifcopenshell.util.element.get_psets(door)
            for pset_name, pset_data in psets.items():
                if 'Width' in pset_data:
                    return float(pset_data['Width'])
        except AttributeError:
            pass
        
        # Fall back to geometry
        try:
            shape = ifcopenshell.geom.create_shape(settings, door)
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            return float(verts[:, 0].max() - verts[:, 0].min())
        except (AttributeError, RuntimeError):
            return 0.9  # Default door width
    
    def is_door_hatch(door) -> bool:
        """Check if door is a hatch."""
        try:
            psets = ifcopenshell.util.element.get_psets(door)
            for pset_name, pset_data in psets.items():
                if 'OperationType' in pset_data:
                    if pset_data['OperationType'] == 'HATCH':
                        return True
        except AttributeError:
            pass
        return False
    
    def boxes_intersect(min1: np.ndarray, max1: np.ndarray, 
                       min2: np.ndarray, max2: np.ndarray, 
                       tolerance: float = 0.01) -> bool:
        """Check if two 3D bounding boxes intersect with tolerance."""
        return (min1[0] < max2[0] + tolerance and max1[0] > min2[0] - tolerance and
                min1[1] < max2[1] + tolerance and max1[1] > min2[1] - tolerance and
                min1[2] < max2[2] + tolerance and max1[2] > min2[2] - tolerance)
    
    # Pre-compute bounding boxes for building elements
    element_bounds = []
    geometry_errors = 0
    
    for elem in model.by_type('IfcBuildingElement'):
        try:
            shape = ifcopenshell.geom.create_shape(settings, elem)
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            elem_min = verts.min(axis=0)
            elem_max = verts.max(axis=0)
            element_bounds.append((elem.GlobalId, elem_min, elem_max))
        except (AttributeError, RuntimeError):
            geometry_errors += 1
            continue
    
    # Check each door for clearance violations
    violating_doors = []
    skipped = 0
    placement_errors = 0
    
    for door in doors:
        # Skip hatches
        if is_door_hatch(door):
            skipped += 1
            continue
        
        # Get door width
        width = get_door_width(door)
        if width is None:
            continue
        
        # Get door placement
        try:
            matrix = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
        except (AttributeError, RuntimeError):
            placement_errors += 1
            continue
        
        # Create clearance zone
        clearance_width = width + WIDTH_ADJUSTMENT
        half_w = clearance_width / 2
        
        # Clearance zone corners in local coordinates (Y is forward direction)
        local_corners = np.array([
            [-half_w, 0, 0],
            [half_w, 0, 0],
            [-half_w, CLEARANCE_DEPTH, 0],
            [half_w, CLEARANCE_DEPTH, 0],
        ])
        
        # Transform to world coordinates
        world_corners = []
        for corner in local_corners:
            world_v = np.dot(matrix, np.append(corner, 1))[:3]
            world_corners.append(world_v)
        
        world_corners = np.array(world_corners)
        clearance_min = world_corners.min(axis=0)
        clearance_max = world_corners.max(axis=0)
        clearance_min[2] = 0
        clearance_max[2] = DOOR_HEIGHT
        
        # Check for intersecting elements
        has_violation = False
        
        for elem_guid, elem_min, elem_max in element_bounds:
            # Skip the door itself
            if elem_guid == door.GlobalId:
                continue
            
            # Check intersection
            if boxes_intersect(clearance_min, clearance_max, elem_min, elem_max):
                has_violation = True
                break
        
        if has_violation:
            violating_doors.append(door.GlobalId)
    
    # Print summary of processing
    if placement_errors > 0:
        print(f"Warning: Skipped {placement_errors} doors due to placement errors")
    if geometry_errors > 0:
        print(f"Warning: Skipped {geometry_errors} elements due to geometry errors")
    if skipped > 0:
        print(f"Info: Skipped {skipped} doors (hatches)")
    
    return violating_doors