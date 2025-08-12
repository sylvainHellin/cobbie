import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any

def get_element_material_layer_thicknesses(
    model_path: str,
    element_type: str = "IfcWall",
    element_name_pattern: str = None,
    material_name_pattern: str = None,
    return_element_info: bool = True
) -> List[Dict[str, Any]]:
    """
    Retrieves material layer thicknesses for specific materials within building elements from IFC models.
    
    Args:
        model_path (str): Path to the IFC model file
        element_type (str, optional): IFC element type to analyze (default: "IfcWall")
        element_name_pattern (str, optional): Pattern to filter elements by name
        material_name_pattern (str, optional): Pattern to filter materials by name
        return_element_info (bool, optional): Whether to include element identification info
    
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing element and material layer information
            - element_name: Name of the element (included if return_element_info is True)
            - element_guid: GlobalId of the element (included if return_element_info is True)
            - material_name: Name of the material
            - layer_thickness: Thickness of the material layer
            - layer_position: Position of the layer in the layer set (0-indexed)
    
    The function handles common IFC material representation patterns including IfcMaterialLayerSetUsage
    and IfcMaterialLayerSet. It assumes that material layers are properly defined in the IFC model
    according to the IFC schema.
    
    Note:
        This function requires IfcOpenShell to be installed and accessible.
        For elements with multiple material representations, only the first valid layer set is processed.
    """
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get elements of specified type
    elements = model.by_type(element_type)
    
    # Filter elements by name pattern if provided
    if element_name_pattern:
        elements = [elem for elem in elements if elem.Name and element_name_pattern.lower() in elem.Name.lower()]
    
    results = []
    
    # Process each element
    for element in elements:
        # Get the material of the element
        material = ifcopenshell.util.element.get_material(element)
        
        if not material:
            continue
            
        # Handle different material representation types
        layer_set = None
        if material.is_a("IfcMaterialLayerSetUsage") and material.ForLayerSet:
            layer_set = material.ForLayerSet
        elif material.is_a("IfcMaterialLayerSet"):
            layer_set = material
            
        # If we have a layer set, process its layers
        if layer_set:
            layers = layer_set.MaterialLayers
            
            for i, layer in enumerate(layers):
                # Get material name
                material_name = None
                if layer.Material:
                    material_name = layer.Material.Name
                    
                # Filter by material name pattern if provided
                if material_name_pattern:
                    if not material_name or material_name_pattern.lower() not in material_name.lower():
                        continue
                
                # Create result entry
                result_entry = {}
                if return_element_info:
                    result_entry.update({
                        "element_name": element.Name,
                        "element_guid": element.GlobalId
                    })
                
                result_entry.update({
                    "material_name": material_name,
                    "layer_thickness": layer.LayerThickness,
                    "layer_position": i  # Position in the layer set (0-indexed)
                })
                
                results.append(result_entry)
    
    return results