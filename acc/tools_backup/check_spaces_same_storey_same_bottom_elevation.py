import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
from typing import List


def check_spaces_same_storey_same_bottom_elevation(path_ifc_model: str) -> List[str]:
    """
    Check that spaces in the same building storey have the same bottom elevation.
    
    This rule validates that all IfcSpace elements within a single IfcBuildingStorey
    share the same bottom elevation value. Spaces in storeys with varying bottom
    elevations are considered violations.

    Args:
        path_ifc_model (str): The file path to the IFC model.

    Returns:
        List[str]: A list of IFC GUIDs of all spaces that violate this rule.
                   Returns an empty list if all spaces in each storey have
                   consistent bottom elevations, or if no spaces are found.

    Example:
        >>> violating_guids = check_spaces_same_storey_same_bottom_elevation('model.ifc')
        >>> print(f"Found {len(violating_guids)} spaces with inconsistent bottom elevations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    violating_guids: List[str] = []
    skipped = 0
    
    settings = ifcopenshell.geom.settings()
    
    # Iterate through all building storeys
    for storey in model.by_type('IfcBuildingStorey'):
        # Get all elements decomposed by this storey
        elements = ifcopenshell.util.element.get_decomposition(storey)
        spaces = [e for e in elements if e.is_a() == 'IfcSpace']
        
        if not spaces:
            continue
        
        space_elevations = []
        
        # Calculate bottom elevation for each space
        for space in spaces:
            try:
                # Get geometry to determine bottom elevation
                shape = ifcopenshell.geom.create_shape(settings, space)
                verts = shape.geometry.verts
                
                # Extract Z coordinates from vertices (array is [x1,y1,z1, x2,y2,z2, ...])
                z_coords = [verts[i+2] for i in range(0, len(verts), 3)]
                bottom_elevation = round(min(z_coords), 2)
                
                space_elevations.append({
                    'elevation': bottom_elevation,
                    'guid': space.GlobalId
                })
            except (AttributeError, RuntimeError) as e:
                # Skip spaces with geometry errors
                skipped += 1
                continue
        
        # Check if all elevations in this storey are the same
        unique_elevations = set(s['elevation'] for s in space_elevations)
        
        if len(unique_elevations) > 1:
            # Storey has spaces with different bottom elevations - all are violations
            for space_data in space_elevations:
                violating_guids.append(space_data['guid'])
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} spaces due to geometry errors")
    
    return violating_guids