
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def get_material_property_by_type_from_elements(
    ifc_file_path: str, 
    element_type: str, 
    material_type_keywords: List[str], 
    property_name: str, 
    element_name_pattern: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves specific properties of materials matching certain types from elements of a specified type in an IFC model.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_type (str): The IFC element type to search within (e.g., 'IfcWall', 'IfcSlab')
        material_type_keywords (List[str]): Keywords to identify the material type of interest (e.g., ['insulation', 'insul'])
        property_name (str): The material property to extract (e.g., 'thickness', 'thermal_conductivity')
        element_name_pattern (Optional[str]): Optional pattern to filter elements by name (e.g., 'exterior')
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing element and material information
    """
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Get all elements of the specified type
    elements = ifc_file.by_type(element_type)
    
    # Filter elements by name pattern if provided
    if element_name_pattern:
        elements = [e for e in elements if hasattr(e, 'Name') and e.Name and element_name_pattern.lower() in e.Name.lower()]
    
    results = []
    
    # Process each element
    for element in elements:
        # Get material information for the element
        material_rel = ifcopenshell.util.element.get_material(element)
        
        if not material_rel:
            continue
            
        # Handle different types of material associations
        materials = []
        if material_rel.is_a("IfcMaterial"):
            materials = [material_rel]
        elif material_rel.is_a("IfcMaterialLayerSetUsage"):
            layer_set = material_rel.ForLayerSet
            if layer_set:
                materials = [layer.Material for layer in layer_set.MaterialLayers if layer.Material]
        elif material_rel.is_a("IfcMaterialLayerSet"):
            materials = [layer.Material for layer in material_rel.MaterialLayers if layer.Material]
        elif material_rel.is_a("IfcMaterialList"):
            materials = material_rel.Materials
            
        # Process each material
        for material in materials:
            if not material or not material.Name:
                continue
                
            # Check if material matches any of the keywords
            material_name = material.Name
            if any(keyword.lower() in material_name.lower() for keyword in material_type_keywords):
                # Extract the requested property
                property_value = None
                property_unit = None
                layer_info = None
                
                # Handle different property types
                if property_name.lower() == "thickness":
                    # For thickness, we need to look at the material layer information
                    if material_rel.is_a("IfcMaterialLayerSetUsage"):
                        layer_set = material_rel.ForLayerSet
                        if layer_set:
                            for layer in layer_set.MaterialLayers:
                                if layer.Material == material:
                                    property_value = layer.LayerThickness
                                    layer_info = {
                                        "layer_name": layer.Name if hasattr(layer, 'Name') else None,
                                        "layer_description": layer.Description if hasattr(layer, 'Description') else None,
                                        "layer_thickness": layer.LayerThickness
                                    }
                                    break
                    elif material_rel.is_a("IfcMaterialLayerSet"):
                        for layer in material_rel.MaterialLayers:
                            if layer.Material == material:
                                property_value = layer.LayerThickness
                                layer_info = {
                                    "layer_name": layer.Name if hasattr(layer, 'Name') else None,
                                    "layer_description": layer.Description if hasattr(layer, 'Description') else None,
                                    "layer_thickness": layer.LayerThickness
                                }
                                break
                
                # Add result to list
                results.append({
                    "element_name": element.Name if hasattr(element, 'Name') and element.Name else "Unnamed",
                    "element_guid": element.GlobalId,
                    "material_name": material_name,
                    "property_value": property_value,
                    "property_unit": property_unit,
                    "layer_info": layer_info
                })
    
    return results
