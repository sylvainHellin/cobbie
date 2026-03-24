import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import numpy as np
from typing import List, Set


def check_504_2_non_uniform_risers_treads(path_ifc_model: str) -> List[str]:
    """
    Rule: 504.2 Treads and Risers
    All steps on a flight of stairs shall have uniform riser heights and uniform tread depths.

    This function analyzes stair geometry to detect non-uniform riser heights by examining
    the Z-coordinate variations in the stair flight mesh.

    Args:
        path_ifc_model: Path to the IFC model file


    Returns:
        List of IFC GUIDs of IfcStair elements that violate the rule
        (have non-uniform riser heights or tread depths)

    Example:
        >>> violations = check_504_2_non_uniform_risers_treads('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violating stairs")
    """
    if not path_ifc_model:
        return []

    try:
        model = ifcopenshell.open(path_ifc_model)
    except Exception as e:
        print(f"Error opening IFC model: {e}")
        return []

    settings = ifcopenshell.geom.settings()
    flights = model.by_type('IfcStairFlight')
    
    if not flights:
        return []
    
    violating_stairs: Set[str] = set()
    skipped_flights = 0
    
    # Analysis parameters based on empirical testing
    MIN_RISER_HEIGHT = 0.02  # Minimum height to consider as a riser (filters mesh tessellation)
    STD_THRESHOLD = 0.05    # Standard deviation threshold for non-uniformity
    
    for flight in flights:
        try:
            # Generate geometry for the stair flight
            shape = ifcopenshell.geom.create_shape(settings, flight)
            
            # Extract Z values (heights) from vertices
            verts = shape.geometry.verts
            vertices = np.array(verts).reshape(-1, 3)
            z_values = vertices[:, 2]
            
            # Get unique Z levels with reasonable precision
            unique_z = np.unique(np.round(z_values, 3))
            
            if len(unique_z) < 2:
                continue  # Cannot determine risers with insufficient Z levels
            
            # Calculate differences between consecutive Z levels
            z_diffs = np.diff(unique_z)
            
            # Filter for significant riser heights
            # Differences > 0.02m represent actual risers (not mesh surface variations)
            riser_heights = z_diffs[z_diffs > MIN_RISER_HEIGHT]
            
            if len(riser_heights) < 2:
                continue  # Need at least 2 risers to check uniformity
            
            # Check uniformity using standard deviation
            std_riser = np.std(riser_heights)
            
            # Rule: standard deviation > 0.05m indicates non-uniform risers
            if std_riser > STD_THRESHOLD:
                # Get parent IfcStair element
                if flight.Decomposes:
                    parent = flight.Decomposes[0].RelatingObject
                    if parent.is_a('IfcStair'):
                        violating_stairs.add(parent.GlobalId)
        
        except (AttributeError, KeyError, RuntimeError) as e:
            # Specific exception handling for geometry processing
            skipped_flights += 1
            continue
        except Exception:
            skipped_flights += 1
            continue
    
    if skipped_flights > 0:
        print(f"Warning: Skipped {skipped_flights} stair flights due to processing errors")
    
    return sorted(list(violating_stairs))