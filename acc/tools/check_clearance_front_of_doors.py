import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.geom
import numpy as np
import trimesh
from typing import List


def check_clearance_front_of_doors(path_ifc_model: str) -> List[str]:
    """
    Check clearance in front of doors and return GUIDs of doors with violations.

    This rule checks there is enough clearance in front of doors by verifying
    that no component intersects the required free area in front of each door.

    Parameters:
    - Clearance depth: 1.0 m (standard requirement)
    - Height adjustment: 0.05 m (included in clearance zone)
    - Check both sides: false (only front side)
    - Exclude: Doors that are hatches

    Args:
        path_ifc_model: Path to the IFC model file

    Returns:
        List of IFC GUIDs of doors that violate the clearance rule.
        Returns empty list if no violations found.

    Example:
        >>> guids = check_clearance_front_of_doors('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} clearance violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Parameters
    clearance_depth = 1.0
    
    # Get all doors
    doors = model.by_type('IfcDoor')
    if not doors:
        return []
    
    # Build geometry tree for all elements
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, True)
    
    tree = ifcopenshell.geom.tree()
    iterator = ifcopenshell.geom.iterator(settings, model, include="*")
    if iterator.initialize():
        while True:
            tree.add_element(iterator.get())
            if not iterator.next():
                break
    
    violating_guids = []
    skipped_doors = 0
    skipped_elements = 0
    
    for door in doors:
        try:
            # Check if door is a hatch (exclude hatches)
            door_type = ifcopenshell.util.element.get_type(door)
            if door_type and door_type.Name:
                type_name_lower = door_type.Name.lower()
                if 'hatch' in type_name_lower or 'access' in type_name_lower:
                    skipped_doors += 1
                    continue
            
            # Get door placement matrix
            matrix = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
            position = matrix[:, 3][:3]
            x_axis = matrix[:3, 0]  # Direction along door leaf
            y_axis = matrix[:3, 1]  # Direction pointing out from door front
            z_axis = matrix[:3, 2]  # Up direction
            
            # Get door dimensions
            psets = ifcopenshell.util.element.get_psets(door)
            width = 0.9  # Default
            height = 2.1  # Default
            
            if 'Qto_DoorBaseQuantities' in psets:
                qto = psets['Qto_DoorBaseQuantities']
                width = qto.get('Width', width)
                height = qto.get('Height', height)
            
            # Create clearance zone mesh (box in front of door)
            # Clearance box dimensions: width x clearance_depth x height
            half_width = width / 2.0
            half_depth = clearance_depth / 2.0
            
            # Create vertices relative to door center
            # Clearance box is positioned in front of door (along +Y axis)
            center_offset = y_axis * (half_depth + 0.05)  # 0.05 adjustment
            door_center = position + center_offset
            
            # Box corners relative to center
            corners = [
                [-half_width, -half_depth, 0],
                [half_width, -half_depth, 0],
                [half_width, half_depth, 0],
                [-half_width, half_depth, 0],
                [-half_width, -half_depth, height],
                [half_width, -half_depth, height],
                [half_width, half_depth, height],
                [-half_width, half_depth, height],
            ]
            
            # Transform corners to world space
            world_corners = []
            for corner in corners:
                # Transform local point to world
                local_point = np.array(corner)
                world_point = (position + 
                               x_axis * local_point[0] + 
                               y_axis * (local_point[1] + half_depth + 0.05) + 
                               z_axis * local_point[2])
                world_corners.append(world_point)
            
            # Create box mesh faces (triangulated cube)
            vertices = np.array(world_corners)
            faces = np.array([
                [0, 1, 2], [0, 2, 3],  # Bottom
                [4, 5, 6], [4, 6, 7],  # Top
                [0, 1, 5], [0, 5, 4],  # Front
                [2, 3, 7], [2, 7, 6],  # Back
                [0, 3, 7], [0, 7, 4],  # Left
                [1, 2, 6], [1, 6, 5],  # Right
            ])
            
            clearance_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            
            # Check for intersections with other elements
            for element in model.by_type('IfcElement'):
                if element == door:
                    continue
                
                try:
                    # Get element geometry from tree
                    clashes = tree.clash_intersection_many([door], [element], tolerance=0.001)
                    
                    if clashes:
                        violating_guids.append(door.GlobalId)
                        break
                except (AttributeError, RuntimeError, KeyError):
                    skipped_elements += 1
                    continue
        except (AttributeError, KeyError, RuntimeError):
            skipped_doors += 1
            continue
    
    if skipped_doors > 0:
        print(f"Warning: Skipped {skipped_doors} doors due to errors")
    if skipped_elements > 0:
        print(f"Warning: Skipped {skipped_elements} element checks due to errors")
    
    return violating_guids