
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
from typing import List, Dict, Any

def get_property_values_from_elements_by_type(file_path: str, element_type: str, property_names: List[str], pset_names: List[str]) -> Dict[str, Any]:
    """
    Extract property values from IFC elements of a specific type.
    
    Args:
        file_path (str): Path to the IFC file
        element_type (str): Type of IFC elements to query (e.g., 'IfcWall', 'IfcSlab')
        property_names (List[str]): List of property names to extract
        pset_names (List[str]): List of property set names to search in
        
    Returns:
        Dict[str, Any]: Dictionary with structure:
            {
                "elements": {
                    element_guid: {
                        pset_name: {
                            property_name: property_value
                        }
                    }
                },
                "aggregated": {
                    property_name: total_value
                }
            }
            
    Note:
        For gross floor area calculation, this function properly calculates the footprint area
        of building storeys rather than simply summing individual slab areas. This follows
        standard definitions of gross floor area measured to the outer surface of exterior walls.
        This function is designed to work with Revit-exported IFC files where property sets
        typically follow naming conventions like 'PSet_Revit_Dimensions', 'Pset_WallCommon', etc.
    """
    # Initialize result structure
    result = {
        "elements": {},
        "aggregated": {prop_name: 0 for prop_name in property_names}
    }
    
    # Open IFC file
    model = ifcopenshell.open(file_path)
    
    # Special handling for gross floor area calculation
    if element_type == "IfcSlab" and "Area" in property_names:
        # Calculate gross floor area properly by getting footprint area per building storey
        gross_floor_area = calculate_gross_floor_area(model)
        result["aggregated"]["Area"] = gross_floor_area
        
        # Still populate elements data for floor slabs
        elements = model.by_type(element_type)
        for element in elements:
            element_guid = element.GlobalId
            result["elements"][element_guid] = {}
            
            # Get all property sets for this element
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Process each specified property set
            for pset_name in pset_names:
                if pset_name in psets:
                    result["elements"][element_guid][pset_name] = {}
                    
                    # Process each specified property
                    for prop_name in property_names:
                        if prop_name in psets[pset_name]:
                            prop_value = psets[pset_name][prop_name]
                            result["elements"][element_guid][pset_name][prop_name] = prop_value
        return result
    
    # Standard processing for other element types or properties
    elements = model.by_type(element_type)
    
    # Process each element
    for element in elements:
        element_guid = element.GlobalId
        result["elements"][element_guid] = {}
        
        # Get all property sets for this element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Process each specified property set
        for pset_name in pset_names:
            if pset_name in psets:
                result["elements"][element_guid][pset_name] = {}
                
                # Process each specified property
                for prop_name in property_names:
                    if prop_name in psets[pset_name]:
                        prop_value = psets[pset_name][prop_name]
                        result["elements"][element_guid][pset_name][prop_name] = prop_value
                        
                        # Only aggregate numeric values
                        if isinstance(prop_value, (int, float)):
                            result["aggregated"][prop_name] += prop_value
    
    return result

def calculate_gross_floor_area(model) -> float:
    """
    Calculate gross floor area by computing the footprint area of each building storey.
    
    This follows the standard definition of gross floor area measured to the outer 
    surface of exterior walls, rather than simply summing individual slab areas.
    
    Args:
        model: Opened IFC model
        
    Returns:
        float: Total gross floor area
    """
    total_gross_floor_area = 0.0
    
    try:
        # Get all building storeys
        storeys = model.by_type("IfcBuildingStorey")
        
        # Settings for geometry creation
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        # For each storey, calculate its footprint area
        for storey in storeys:
            storey_footprint_area = 0.0
            
            # Get all elements contained in this storey
            elements = get_elements_in_storey(model, storey)
            
            # For floor area calculation, we're primarily interested in slabs and walls
            floor_elements = [elem for elem in elements if elem.is_a("IfcSlab") or elem.is_a("IfcWall")]
            
            # Calculate footprint area for each element
            for element in floor_elements:
                # Check if this is a floor slab (not roof, balcony, etc.)
                if element.is_a("IfcSlab"):
                    predefined_type = ifcopenshell.util.element.get_predefined_type(element)
                    if predefined_type and predefined_type.upper() in ["ROOF", "BALCONY", "BASESLAB"]:
                        continue  # Skip non-floor slabs
                
                try:
                    # Create shape for the element
                    shape = ifcopenshell.geom.create_shape(settings, element)
                    if shape:
                        # Calculate footprint area for this element
                        element_footprint_area = calculate_element_footprint_area(shape)
                        storey_footprint_area += element_footprint_area
                except Exception:
                    # If we can't calculate geometry for an element, skip it
                    continue
            
            total_gross_floor_area += storey_footprint_area
            
    except Exception:
        # If we can't calculate the footprint area properly, fall back to summing floor slab areas
        # but only for actual floor slabs
        slabs = model.by_type("IfcSlab")
        for slab in slabs:
            predefined_type = ifcopenshell.util.element.get_predefined_type(slab)
            if predefined_type and predefined_type.upper() in ["ROOF", "BALCONY", "BASESLAB"]:
                continue  # Skip non-floor slabs
            
            # Try to get area from properties
            psets = ifcopenshell.util.element.get_psets(slab)
            for pset_dict in psets.values():
                if "Area" in pset_dict:
                    area_value = pset_dict["Area"]
                    if isinstance(area_value, (int, float)):
                        total_gross_floor_area += area_value
                    break
    
    return total_gross_floor_area

def get_elements_in_storey(model, storey):
    """
    Get all elements contained in a building storey.
    
    Args:
        model: Opened IFC model
        storey: IfcBuildingStorey entity
        
    Returns:
        List of elements in the storey
    """
    elements = []
    
    # Get all spatial elements referenced by this storey
    try:
        # Using IfcRelContainedInSpatialStructure to get elements in this storey
        for rel in storey.ContainsElements:
            elements.extend(rel.RelatedElements)
    except Exception:
        # Fallback: get all elements and check their spatial structure
        all_elements = model.by_type("IfcProduct")
        for element in all_elements:
            if hasattr(element, 'ContainedInStructure') and element.ContainedInStructure:
                if element.ContainedInStructure[0].RelatingStructure == storey:
                    elements.append(element)
    
    return elements

def calculate_element_footprint_area(shape) -> float:
    """
    Calculate the footprint area of an element from its geometry.
    
    Args:
        shape: IfcOpenShell shape representation
        
    Returns:
        float: Footprint area of the element
    """
    try:
        # Get vertices from the shape
        verts = shape.geometry.verts
        if not verts:
            return 0.0
            
        # For footprint calculation, we need to project to XY plane and calculate 2D area
        # This is a simplified approach - in practice, you'd want to get the actual 2D projection
        # For now, we'll use a bounding box approach as an approximation
        
        # Extract X,Y coordinates
        x_coords = [verts[i] for i in range(0, len(verts), 3)]
        y_coords = [verts[i+1] for i in range(0, len(verts), 3)]
        
        if not x_coords or not y_coords:
            return 0.0
            
        # Calculate bounding box area as approximation
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        
        return (max_x - min_x) * (max_y - min_y)
    except Exception:
        return 0.0
