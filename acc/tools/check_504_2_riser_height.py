import ifcopenshell
import ifcopenshell.util.element
from typing import List

def check_504_2_riser_height(path_ifc_model: str) -> List[str]:
    """
    Check if stair riser heights meet the requirements (min 0.1m, max 0.18m).
    
    Rule 504.2 Treads and Risers: Risers shall be 4 inches (100 mm) high minimum
    and 7 inches (180 mm) high maximum.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of all elements (stairs and related components) that violate
        the riser height requirements. This includes the violating stair/flight elements
        and all elements decomposed by them (flights, railings, stringers, etc.).
        
    Example:
        >>> guids = check_504_2_riser_height('/path/to/model.ifc')
        >>> print(f'Found {len(guids)} violations')
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Define riser height limits (in meters)
    MIN_RISER_HEIGHT = 0.1  # 100 mm
    MAX_RISER_HEIGHT = 0.18  # 180 mm
    
    violating_guids = set()
    skipped = 0
    
    def get_riser_height(element):
        """Get riser height from element property sets."""
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Check common property sets
            for pset_name in ['Pset_StairCommon', 'Pset_StairFlightCommon']:
                if pset_name in psets:
                    riser = psets[pset_name].get('RiserHeight')
                    if riser is not None:
                        return riser
            
            # Check type properties
            elem_type = ifcopenshell.util.element.get_type(element)
            if elem_type:
                type_psets = ifcopenshell.util.element.get_psets(elem_type)
                for pset_name in ['Pset_StairCommon', 'Pset_StairFlightCommon']:
                    if pset_name in type_psets:
                        riser = type_psets[pset_name].get('RiserHeight')
                        if riser is not None:
                            return riser
            return None
        except (AttributeError, KeyError):
            return None
    
    def add_violating_stair_elements(stair):
        """Add stair and all its decomposed elements to violations set."""
        violating_guids.add(stair.GlobalId)
        if hasattr(stair, 'IsDecomposedBy'):
            for rel in stair.IsDecomposedBy:
                if hasattr(rel, 'RelatedObjects'):
                    for obj in rel.RelatedObjects:
                        violating_guids.add(obj.GlobalId)
    
    # Check IfcStair elements
    for stair in model.by_type('IfcStair'):
        try:
            riser_height = get_riser_height(stair)
            
            if riser_height is not None:
                if riser_height < MIN_RISER_HEIGHT or riser_height > MAX_RISER_HEIGHT:
                    add_violating_stair_elements(stair)
        except (AttributeError, KeyError):
            skipped += 1
            continue
    
    # Check IfcStairFlight elements directly (standalone flights not decomposed by stairs)
    for flight in model.by_type('IfcStairFlight'):
        try:
            # Skip if already part of a violating stair
            if flight.GlobalId in violating_guids:
                continue
                
            riser_height = get_riser_height(flight)
            
            if riser_height is not None:
                if riser_height < MIN_RISER_HEIGHT or riser_height > MAX_RISER_HEIGHT:
                    violating_guids.add(flight.GlobalId)
                    # Also add related elements of the flight
                    if hasattr(flight, 'IsDecomposedBy'):
                        for rel in flight.IsDecomposedBy:
                            if hasattr(rel, 'RelatedObjects'):
                                for obj in rel.RelatedObjects:
                                    violating_guids.add(obj.GlobalId)
        except (AttributeError, KeyError):
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to missing attributes")
    
    return sorted(list(violating_guids))