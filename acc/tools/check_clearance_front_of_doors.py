import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.shape
import ifcopenshell.geom
import numpy as np
import trimesh
from typing import List, Optional, Tuple


def is_hatch(door) -> bool:
    """Check if a door is a hatch (should be excluded from clearance check)."""
    try:
        psets = ifcopenshell.util.element.get_psets(door)
        for pset_name, pset in psets.items():
            if 'hatch' in str(pset).lower():
                return True
    except Exception:
        pass
    
    try:
        if door.IsTypedBy:
            for rel in door.IsTypedBy:
                if hasattr(rel, 'RelatingType'):
                    type_obj = rel.RelatingType
                    if hasattr(type_obj, 'Name') and 'hatch' in str(type_obj.Name).lower():
                        return True
    except Exception:
        pass
    return False


def get_door_clearance_box(
    door, 
    clearance_depth: float = 0.6,
    width_multiplier: float = 1.0,
    height_adjustment: float = 0.05
) -> Optional[trimesh.Trimesh]:
    """Create a trimesh box representing the clearance zone in front of a door.
    
    The clearance box extends in front of the door (along local Y axis)
    with dimensions based on the door's width and height.
    
    Args:
        door: The IfcDoor element
        clearance_depth: Depth of clearance zone in meters
        width_multiplier: Multiplier for door width to determine clearance width
        height_adjustment: Additional height added to door height in meters
    
    Returns:
        Trimesh box representing the clearance zone, or None if creation fails
    """
    try:
        matrix = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
        
        # Local axes from placement matrix
        local_x = matrix[:3, 0]  # Width direction
        local_y = matrix[:3, 1]  # Front direction (perpendicular to door)
        local_z = matrix[:3, 2]  # Vertical
        position = matrix[:3, 3]
        
        # Get door dimensions
        width = getattr(door, 'OverallWidth', None)
        height = getattr(door, 'OverallHeight', None)
        
        # Calculate clearance dimensions with defaults
        clearance_width = (width * width_multiplier) if width else 0.9
        clearance_height = (height if height else 2.1) + height_adjustment
        
        # Create box extents (half-sizes)
        extents = [clearance_width / 2, clearance_depth / 2, clearance_height / 2]
        
        # Create box at origin
        box = trimesh.creation.box(extents=extents)
        
        # Position box in front of door (offset by half depth in front direction)
        box_position = position + local_y * (clearance_depth / 2)
        
        # Build transformation matrix for the box
        box_matrix = np.eye(4)
        box_matrix[:3, 3] = box_position
        box_matrix[:3, 0] = local_x
        box_matrix[:3, 1] = local_y
        box_matrix[:3, 2] = local_z
        
        box.apply_transform(box_matrix)
        return box
    except Exception as e:
        return None


def element_to_trimesh(element, settings=None) -> Optional[trimesh.Trimesh]:
    """Convert an IFC element to a trimesh mesh.
    
    Args:
        element: The IFC element to convert
        settings: Optional ifcopenshell.geom.settings object
    
    Returns:
        Trimesh mesh representation of the element, or None if conversion fails
    """
    if settings is None:
        settings = ifcopenshell.geom.settings()
    
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = np.array(shape.geometry.verts).reshape(-1, 3)
        faces = np.array(shape.geometry.faces).reshape(-1, 3)
        
        if len(faces) > 0:
            mesh = trimesh.Trimesh(vertices=verts, faces=faces)
            matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
            mesh.apply_transform(matrix)
            return mesh
    except Exception:
        pass
    return None


def bounding_boxes_intersect(bounds1, bounds2, tolerance=0.001):
    """Check if two bounding boxes intersect.
    
    Args:
        bounds1: First bounding box [[minx, miny, minz], [maxx, maxy, maxz]]
        bounds2: Second bounding box [[minx, miny, minz], [maxx, maxy, maxz]]
        tolerance: Tolerance for intersection check
    
    Returns:
        True if bounding boxes intersect, False otherwise
    """
    return not (
        bounds1[1][0] + tolerance < bounds2[0][0] or
        bounds1[0][0] - tolerance > bounds2[1][0] or
        bounds1[1][1] + tolerance < bounds2[0][1] or
        bounds1[0][1] - tolerance > bounds2[1][1] or
        bounds1[1][2] + tolerance < bounds2[0][2] or
        bounds1[0][2] - tolerance > bounds2[1][2]
    )


def meshes_intersect(mesh1: trimesh.Trimesh, mesh2: trimesh.Trimesh) -> bool:
    """Check if two meshes intersect using collision detection.
    
    Args:
        mesh1: First trimesh mesh
        mesh2: Second trimesh mesh
    
    Returns:
        True if meshes intersect, False otherwise
    """
    if not bounding_boxes_intersect(mesh1.bounds, mesh2.bounds):
        return False
    
    try:
        manager = trimesh.collision.CollisionManager()
        manager.add_object('mesh1', mesh1)
        return manager.in_collision_single(mesh2)
    except Exception:
        pass
    
    return False


def check_clearance_front_of_doors(path_ifc_model: str) -> List[str]:
    """Check clearance in front of doors and return GUIDs of violating elements.
    
    This rule checks if there is enough clearance in front of doors by detecting
    components that intersect the required free area in front of each door.
    
    Parameters:
        - Clearance Depth: 0.6 m
        - Width: Based on door width (multiplier = 1.0)
        - Height Adjustment: 0.05 m
        - Check both sides: False (only front of door)
        - Exclude: Doors that are hatches
    
    Args:
        path_ifc_model: File path to the IFC model
    
    Returns:
        List of IFC GUIDs of elements (components) that violate the clearance rule
        by intersecting the free area in front of doors
    
    Example:
        >>> violations = check_clearance_front_of_doors('model.ifc')
        >>> print(f"Found {len(violations)} clearance violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all doors
    doors = model.by_type('IfcDoor')
    if not doors:
        return []
    
    # Rule parameters
    CLEARANCE_DEPTH = 0.6
    WIDTH_MULTIPLIER = 1.0
    HEIGHT_ADJUSTMENT = 0.05
    
    violating_guids = []
    doors_checked = 0
    doors_excluded = 0
    
    # Get elements to check (exclude spaces, openings, grids)
    elements_to_check = []
    for elem in model:
        if elem.is_a('IfcSpace') or elem.is_a('IfcOpeningElement'):
            continue
        if elem.is_a('IfcGrid') or elem.is_a('IfcAxis2D'):
            continue
        if hasattr(elem, 'Representation') and elem.Representation:
            elements_to_check.append(elem)
    
    if not elements_to_check:
        return []
    
    # Pre-compute element bounding boxes for efficient spatial filtering
    settings = ifcopenshell.geom.settings()
    element_bounds = []
    valid_elements = []
    
    for elem in elements_to_check:
        try:
            shape = ifcopenshell.geom.create_shape(settings, elem)
            matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            transformed_verts = (matrix[:3, :3] @ verts.T + matrix[:3, 3:4]).T
            bounds = [np.min(transformed_verts, axis=0), np.max(transformed_verts, axis=0)]
            element_bounds.append(bounds)
            valid_elements.append(elem)
        except Exception:
            pass
    
    # Check each door
    for door in doors:
        if is_hatch(door):
            doors_excluded += 1
            continue
        
        doors_checked += 1
        
        try:
            # Create clearance box for this door
            clearance_box = get_door_clearance_box(
                door, CLEARANCE_DEPTH, WIDTH_MULTIPLIER, HEIGHT_ADJUSTMENT
            )
            
            if clearance_box is None:
                continue
            
            # Find elements spatially near the clearance box
            nearby_indices = []
            for i, bounds in enumerate(element_bounds):
                if bounding_boxes_intersect(clearance_box.bounds, bounds, tolerance=0.1):
                    nearby_indices.append(i)
            
            # Check intersections with nearby elements
            for idx in nearby_indices:
                elem = valid_elements[idx]
                if elem.id == door.id:
                    continue
                
                mesh = element_to_trimesh(elem, settings)
                if mesh and meshes_intersect(clearance_box, mesh):
                    violating_guids.append(elem.GlobalId)
                    
        except Exception:
            continue
    
    return violating_guids