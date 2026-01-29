import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.classification
import ifcopenshell.geom
from typing import List
import numpy as np


def check_305_3_size(ifc_file_path: str) -> List[str]:
    """
    Rule: 305.3 Size - Check if clear floor/ground spaces meet minimum size requirements.
    
    The clear floor or ground space shall be 30 inches (760 mm) minimum by 
    48 inches (1220 mm) minimum.
    
    Applicable Space Classifications: Balcony, Circulation, Garage, Habitable, 
    Institutional, Lobby, Mercantile, Office, Parking, Production, Refuge, 
    Stair Hall, Workplace
    
    Args:
        ifc_file_path: Path to the IFC file to analyze
        
    Returns:
        List of IFC GUIDs of spaces that violate the size requirement
        
    Example:
        >>> violations = check_305_3_size('model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
        
        # Define minimum dimensions in millimeters
        MIN_WIDTH_MM = 760  # 30 inches
        MIN_DEPTH_MM = 1220  # 48 inches
        
        # Applicable classifications (case-insensitive matching)
        applicable_classifications = {
            'BALCONY', 'CIRCULATION', 'GARAGE', 'HABITABLE', 'INSTITUTIONAL',
            'LOBBY', 'MERCANTILE', 'OFFICE', 'PARKING', 'PRODUCTION', 
            'REFUGE', 'STAIR HALL', 'STAIRHALL', 'WORKPLACE'
        }
        
        violations = []
        
        # Get all spaces
        spaces = ifc_file.by_type('IfcSpace')
        
        # Setup geometry settings
        settings = ifcopenshell.geom.settings()
        
        for space in spaces:
            try:
                # Get space classification from various sources
                classification = None
                
                # Check LongName
                if hasattr(space, 'LongName') and space.LongName:
                    classification = space.LongName
                
                # Check Name if no classification found
                if not classification and hasattr(space, 'Name') and space.Name:
                    classification = space.Name
                
                # Check ObjectType if no classification found
                if not classification and hasattr(space, 'ObjectType') and space.ObjectType:
                    classification = space.ObjectType
                
                # Check classification references
                if not classification:
                    refs = ifcopenshell.util.classification.get_references(space)
                    if refs:
                        for ref in refs:
                            if hasattr(ref, 'Name') and ref.Name:
                                classification = ref.Name
                                break
                
                # If still no classification, try to get from property sets
                if not classification:
                    psets = ifcopenshell.util.element.get_psets(space)
                    for pset_name, pset_data in psets.items():
                        if 'Reference' in pset_data or 'Type' in pset_data:
                            classification = pset_data.get('Reference') or pset_data.get('Type')
                            if classification:
                                break
                
                # Check if classification is applicable (case-insensitive)
                is_applicable = False
                if classification:
                    classification_upper = classification.upper().replace(' ', '')
                    for app_class in applicable_classifications:
                        if app_class.replace(' ', '') in classification_upper:
                            is_applicable = True
                            break
                
                # Skip if not applicable
                if not is_applicable:
                    continue
                
                # Get geometry for the space
                shape = ifcopenshell.geom.create_shape(settings, space)
                
                # Get vertices
                verts = shape.geometry.verts
                
                # Convert to numpy array and reshape
                verts_array = np.array(verts).reshape(-1, 3)
                
                # Calculate bounding box
                min_coords = np.min(verts_array, axis=0)
                max_coords = np.max(verts_array, axis=0)
                
                # Calculate dimensions (convert from meters to mm)
                x_dim = (max_coords[0] - min_coords[0]) * 1000
                y_dim = (max_coords[1] - min_coords[1]) * 1000
                z_dim = (max_coords[2] - min_coords[2]) * 1000
                
                # The width and depth are the two largest dimensions
                # (to handle rotated spaces where X/Y may not align with width/depth)
                dimensions = sorted([x_dim, y_dim, z_dim])
                width_mm = dimensions[1]  # Middle value
                depth_mm = dimensions[2]  # Largest value
                
                # Check if dimensions meet requirements
                if width_mm < MIN_WIDTH_MM or depth_mm < MIN_DEPTH_MM:
                    if space.GlobalId:
                        violations.append(space.GlobalId)
                
            except Exception:
                # Skip spaces that cannot be processed
                continue
        
        return violations
        
    except Exception:
        return []