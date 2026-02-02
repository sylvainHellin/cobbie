import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
from typing import List


def check_304_3_1_circular_space(path_ifc_model: str) -> List[str]:
    """
    Check if spaces in an IFC model have at least 1.52m diameter for wheelchair turning space.
    
    Rule 304.3.1: Circular space shall have a diameter of 1.52 m (60 inches) minimum.
    
    Applicable Space Classifications: Balcony, Circulation, Garage, Habitable, Institutional, 
    Lobby, Mercantile, Office, Parking, Production, Refuge, Stair Hall, Workplace
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of spaces that violate the circular space requirement
        
    Example:
        >>> violations = check_304_3_1_circular_space('model.ifc')
        >>> print(f'Found {len(violations)} violations')
    """
    # Applicable space classifications from the rule
    # Using conservative keyword matching to avoid false positives
    applicable_keywords = {
        'stair', 'stairway', 'stair hall', 'stairhall',
        'refuge', 'balcony'
    }
    
    MIN_DIAMETER = 1.52  # meters
    
    violations = []
    skipped = 0
    
    model = ifcopenshell.open(path_ifc_model)
    spaces = model.by_type('IfcSpace')
    
    if not spaces:
        return []
    
    settings = ifcopenshell.geom.settings()
    
    for space in spaces:
        guid = space.GlobalId
        
        # Check if space should be evaluated based on classification
        should_check = False
        
        # Check LongName attribute (primary classification field)
        longname = getattr(space, 'LongName', None) or ''
        if longname:
            longname_lower = str(longname).lower().strip()
            for keyword in applicable_keywords:
                if keyword in longname_lower:
                    should_check = True
                    break
        
        # Check Name attribute as secondary
        if not should_check:
            name = getattr(space, 'Name', None) or ''
            if name:
                name_lower = str(name).lower().strip()
                for keyword in applicable_keywords:
                    if keyword in name_lower:
                        should_check = True
                        break
        
        # Check psets for classification info
        if not should_check:
            try:
                psets = ifcopenshell.util.element.get_psets(space)
                pset_str = str(psets).lower()
                for keyword in applicable_keywords:
                    if keyword in pset_str:
                        should_check = True
                        break
            except Exception:
                pass
        
        if not should_check:
            continue
        
        # Get geometry and calculate minimum dimension
        try:
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = shape.geometry.verts
            
            if len(verts) == 0:
                skipped += 1
                continue
            
            # Extract vertices
            verts_list = [(verts[i], verts[i+1], verts[i+2]) for i in range(0, len(verts), 3)]
            xs = [v[0] for v in verts_list]
            ys = [v[1] for v in verts_list]
            
            # Calculate bounding box dimensions
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            width = max_x - min_x
            depth = max_y - min_y
            
            # Maximum diameter that can fit is the minimum horizontal dimension
            max_diameter = min(width, depth)
            
            if max_diameter < MIN_DIAMETER:
                violations.append(guid)
                
        except Exception:
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} spaces due to errors")
    
    return violations