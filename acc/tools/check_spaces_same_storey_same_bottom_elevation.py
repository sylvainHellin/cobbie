import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import numpy as np
from typing import List, Dict
from collections import Counter


def check_spaces_same_storey_same_bottom_elevation(path_ifc_model: str) -> List[str]:
    """
    Identifies spaces in the same building storey that do not have the same bottom elevation.
    
    This rule checks that spaces within each building storey have consistent bottom elevations.
    If a storey contains spaces with different bottom elevations, ALL spaces in that storey
    are flagged as violations.

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of spaces that violate the rule (spaces in storeys with
        non-uniform bottom elevations). Returns an empty list if no violations are found
        or if the model contains no spaces.

    Example:
        >>> violations = check_spaces_same_storey_same_bottom_elevation('model.ifc')
        >>> print(f"Found {len(violations)} violating spaces")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all storeys
    storeys = model.by_type('IfcBuildingStorey')
    
    if not storeys:
        return []
    
    # Group spaces by storey using get_decomposition
    storey_spaces: Dict[int, List[Dict]] = {}
    settings = ifcopenshell.geom.settings()
    skipped = 0
    
    for storey in storeys:
        storey_id = storey.id()
        
        # Get all decomposed elements (includes spaces via aggregation hierarchy)
        try:
            elements = ifcopenshell.util.element.get_decomposition(storey)
        except (RuntimeError, AttributeError):
            continue
            
        spaces_in_storey = [e for e in elements if e.is_a('IfcSpace')]
        
        if not spaces_in_storey:
            continue
        
        # Process spaces in this storey
        storey_spaces[storey_id] = []
        for space in spaces_in_storey:
            try:
                # Get geometry to find bottom elevation
                shape = ifcopenshell.geom.create_shape(settings, space)
                verts = shape.geometry.verts
                
                # Reshape flat list to (N, 3) array and find min Z (bottom elevation)
                verts_array = np.array(verts).reshape(-1, 3)
                bottom_elevation = float(verts_array[:, 2].min())
                
                storey_spaces[storey_id].append({
                    'guid': space.GlobalId,
                    'bottom_elevation': bottom_elevation
                })
            except (RuntimeError, AttributeError, ValueError) as e:
                skipped += 1
                continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} spaces due to geometry errors")
    
    # Check each storey for violations
    violating_guids = []
    
    for storey_id, spaces_data in storey_spaces.items():
        if len(spaces_data) < 2:
            continue  # No issue if only 1 space
        
        # Round elevations to 2 decimal places for comparison
        elevations = [round(s['bottom_elevation'], 2) for s in spaces_data]
        unique_elevations = set(elevations)
        
        # If storey has multiple elevations, ALL spaces are violations
        if len(unique_elevations) > 1:
            for s in spaces_data:
                violating_guids.append(s['guid'])
    
    return violating_guids