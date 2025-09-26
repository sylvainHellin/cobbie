import ifcopenshell
import ifcopenshell.util.element
from typing import Dict

def calculate_finish_quantities(model_path: str, space_name: str, finish_type: str) -> Dict[str, float]:
    """
    Calculate the quantity of a specific finish material in a given space.
    
    Args:
        model_path (str): Path to the IFC model file
        space_name (str): Name of the space to analyze
        finish_type (str): Type of finish to calculate (e.g., "tiles", "carpet", "paint")
        
    Returns:
        Dict[str, float]: Dictionary containing:
            - area: Total area of the specified finish in square meters
            - volume: Total volume of the specified finish in cubic meters (if applicable)
            - units: Number of units of the finish (if applicable)
            
    This function assumes the IFC model follows standard conventions where:
    - Finish elements are represented as IfcSlab, IfcCovering, or similar elements
    - Elements have property sets with area/volume information (e.g., PSet_Revit_Dimensions)
    - Elements and spaces are properly associated with building stories (IfcBuildingStorey)
    
    Note: This implementation is specifically tested with Revit-exported IFC models 
    that contain PSet_Revit_Dimensions property sets.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Find the target space by name
    spaces = model.by_type("IfcSpace")
    target_space = None
    for space in spaces:
        if getattr(space, 'Name', '') == space_name:
            target_space = space
            break
    
    if not target_space:
        raise ValueError(f"Space '{space_name}' not found in the model")
    
    # Find elements associated with the target space
    # Check both direct containment and space boundary relationships
    space_elements = set()  # Use set to avoid duplicates
    
    # Check direct containment relationships
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        if rel.RelatingStructure == target_space:
            space_elements.update(rel.RelatedElements)
    
    # Check space boundary relationships
    for rel in model.by_type("IfcRelSpaceBoundary"):
        if rel.RelatingSpace == target_space:
            if rel.RelatedBuildingElement:
                space_elements.add(rel.RelatedBuildingElement)
    
    # Filter elements by finish type and element type
    matching_elements = []
    finish_type_lower = finish_type.lower()
    
    for element in space_elements:
        # Only consider IfcSlab for floor finishes or IfcCovering for wall/ceiling finishes
        if element.is_a() not in ["IfcSlab", "IfcCovering"]:
            continue
            
        # Check if the element name contains the finish type
        element_name = getattr(element, 'Name', '') or ''
        element_name_lower = element_name.lower()
        
        # More precise matching for finish types
        is_match = False
        if finish_type_lower in element_name_lower:
            is_match = True
        elif finish_type_lower == "tiles" and ("tile" in element_name_lower or "ceramic" in element_name_lower):
            is_match = True
        elif finish_type_lower == "carpet" and "carpet" in element_name_lower:
            is_match = True
        elif finish_type_lower == "paint" and "paint" in element_name_lower:
            is_match = True
        elif finish_type_lower == "floor" and "floor" in element_name_lower:
            is_match = True
        elif finish_type_lower == "ceiling" and ("ceiling" in element_name_lower or "cover" in element_name_lower):
            is_match = True
            
        if is_match:
            matching_elements.append(element)
    
    # Calculate total quantities
    total_area = 0.0
    total_volume = 0.0
    
    for element in matching_elements:
        # Get property sets for the element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Look for area and volume in PSet_Revit_Dimensions
        if 'PSet_Revit_Dimensions' in psets:
            dimensions = psets['PSet_Revit_Dimensions']
            if 'Area' in dimensions:
                total_area += dimensions['Area']
            if 'Volume' in dimensions:
                total_volume += dimensions['Volume']
        # Also check for generic quantity sets
        elif 'BaseQuantities' in psets:
            quantities = psets['BaseQuantities']
            if 'Area' in quantities:
                total_area += quantities['Area']
            if 'Volume' in quantities:
                total_volume += quantities['Volume']
    
    # Return the results
    return {
        "area": round(total_area, 6),  # Round to 6 decimal places to avoid floating point issues
        "volume": round(total_volume, 6),
        "units": len(matching_elements)  # Number of finish elements found
    }