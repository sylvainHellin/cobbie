import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import numpy as np
from shapely.geometry import Polygon
from typing import List


def check_504_2_riser_height(path_ifc_model: str) -> List[str]:
    """
    Check stairs for violations of rule 504.2: Riser heights must be between 100mm and 180mm.
    
    This function checks IfcStair and IfcStairFlight elements for riser height violations
    and identifies geometrically associated landing slabs for violating stairs.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of all elements that violate the rule, including:
        - Stairs with riser heights outside the 100mm-180mm range
        - Stair flights with riser heights outside the 100mm-180mm range  
        - Landing slabs geometrically associated with violating stairs
        
    Example:
        >>> violations = check_504_2_riser_height('/path/to/model.ifc')
        >>> print(violations)
        ['guid1', 'guid2', ...]
    """
    model = ifcopenshell.open(path_ifc_model)
    violations = set()
    
    # Define riser height limits (in meters)
    MIN_RISER_HEIGHT = 0.1  # 100 mm
    MAX_RISER_HEIGHT = 0.18  # 180 mm
    
    # Get all relevant elements
    stairs = model.by_type('IfcStair')
    flights = model.by_type('IfcStairFlight')
    slabs = model.by_type('IfcSlab')
    
    if not stairs and not flights:
        return []
    
    settings = ifcopenshell.geom.settings()
    skipped_geometry = 0
    
    def get_riser_height(element):
        """Extract riser height from element property sets."""
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            # Check various property sets that might contain riser height
            for pset_name, props in psets.items():
                if 'RiserHeight' in props:
                    return props['RiserHeight']
                elif 'Actual Riser Height' in props:
                    return props['Actual Riser Height']
        except (AttributeError, KeyError):
            pass
        return None
    
    def has_geometry(elem):
        """Check if element has valid geometry representation."""
        try:
            if hasattr(elem, 'Representation'):
                rep = elem.Representation
                return rep is not None
        except AttributeError:
            return False
    
    def get_element_geometry(elem):
        """Get element geometry as vertices and XY polygon."""
        try:
            if not has_geometry(elem):
                return None, None
            shape = ifcopenshell.geom.create_shape(settings, elem)
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            xy_poly = Polygon(verts[:, :2])
            return verts, xy_poly
        except Exception:
            return None, None
    
    def find_associated_slabs(stair_verts, stair_xy_poly, stair_z_min, stair_z_max, stair_storey):
        """Find slabs that are geometrically associated with stair."""
        associated = []
        
        # First, get all slabs in the same storey as the stair
        storey_slabs = []
        if stair_storey and hasattr(stair_storey, 'ContainsElements'):
            for rel in stair_storey.ContainsElements:
                if hasattr(rel, 'RelatedElements'):
                    for elem in rel.RelatedElements:
                        if elem.is_a() == 'IfcSlab':
                            storey_slabs.append(elem)
        
        # If no storey association, check all slabs
        slabs_to_check = storey_slabs if storey_slabs else slabs
        
        for slab in slabs_to_check:
            slab_verts, slab_xy_poly = get_element_geometry(slab)
            if slab_verts is None or slab_xy_poly is None:
                continue
            
            # Check XY intersection
            if not stair_xy_poly.intersects(slab_xy_poly):
                continue
            
            intersection = stair_xy_poly.intersection(slab_xy_poly)
            # Check if significant overlap (> 0.01 sqm)
            if intersection.area <= 0.01:
                continue
            
            slab_z_min = slab_verts[:, 2].min()
            slab_z_max = slab_verts[:, 2].max()
            
            # Check if slab is at top or bottom of stair (landing)
            # Tolerance: 30cm
            if (abs(slab_z_min - stair_z_max) < 0.3 or 
                abs(slab_z_max - stair_z_min) < 0.3 or
                abs(slab_z_min - stair_z_min) < 0.3):
                associated.append(slab.GlobalId)
        
        return associated
    
    def get_element_storey(elem):
        """Get the storey containing an element."""
        try:
            if hasattr(elem, 'ContainedInStructure'):
                for rel in elem.ContainedInStructure:
                    if hasattr(rel, 'RelatingStructure'):
                        return rel.RelatingStructure
        except AttributeError:
            pass
        return None
    
    # Check IfcStair elements
    for stair in stairs:
        riser_height = get_riser_height(stair)
        
        if riser_height is None:
            continue
        
        # Check if riser height violates rule
        if riser_height < MIN_RISER_HEIGHT or riser_height > MAX_RISER_HEIGHT:
            violations.add(stair.GlobalId)
            
            # Get stair's storey
            stair_storey = get_element_storey(stair)
            
            # Try to find associated landing slabs
            stair_verts, stair_xy_poly = get_element_geometry(stair)
            if stair_verts is not None:
                stair_z_min = stair_verts[:, 2].min()
                stair_z_max = stair_verts[:, 2].max()
                associated_slabs = find_associated_slabs(stair_verts, stair_xy_poly, stair_z_min, stair_z_max, stair_storey)
                for slab_guid in associated_slabs:
                    violations.add(slab_guid)
            else:
                skipped_geometry += 1
    
    # Also check IfcStairFlight elements directly
    for flight in flights:
        riser_height = get_riser_height(flight)
        
        if riser_height is not None:
            if riser_height < MIN_RISER_HEIGHT or riser_height > MAX_RISER_HEIGHT:
                violations.add(flight.GlobalId)
    
    if skipped_geometry > 0:
        print(f"Warning: Skipped geometry analysis for {skipped_geometry} elements")
    
    return sorted(list(violations))