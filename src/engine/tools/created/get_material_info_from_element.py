
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict

def get_material_info_from_element(ifc_file_path: str, element_or_material_association) -> List[Dict[str, str]]:
    """
    Extract material names and properties from various material representations.
    
    This function handles different types of material associations in IFC models:
    - IfcMaterialLayerSetUsage: Extracts materials from layered constructions
    - IfcMaterial: Simple material associations
    - IfcMaterialList: Lists of materials
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_or_material_association: Either an IFC element or a material association
            (IfcMaterialLayerSetUsage, IfcMaterial, or IfcMaterialList)
        
    Returns:
        List[Dict[str, str]]: List of dictionaries containing material information.
            Each dictionary contains:
            - name: Material name
            - description: Material description (if available)
            - thickness: Layer thickness (for IfcMaterialLayerSetUsage)
            - layerSetName: Name of the layer set (for IfcMaterialLayerSetUsage)
            - type: Type of material representation
            
    Example:
        >>> materials = get_material_info_from_element("model.ifc", element)
        >>> print(materials[0]["name"])
        "Roofing - EPDM Membrane"
    """
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Initialize result list
    materials_info = []
    
    # Determine if we're dealing with an element or a material association
    if hasattr(element_or_material_association, 'is_a') and element_or_material_association.is_a().startswith('IfcMaterial'):
        # Direct material association provided
        material_association = element_or_material_association
    else:
        # Element provided, need to find its material association
        material_associations = [assoc for assoc in ifc_file.get_inverse(element_or_material_association) 
                                if assoc.is_a("IfcRelAssociatesMaterial")]
        if not material_associations:
            return []  # No material association found
        material_association = material_associations[0].RelatingMaterial
    
    # Handle different types of material representations
    if material_association.is_a("IfcMaterialLayerSetUsage"):
        # Handle IfcMaterialLayerSetUsage
        layer_set = material_association.ForLayerSet
        layer_set_name = getattr(layer_set, 'LayerSetName', 'Unnamed Layer Set')
        
        for layer in layer_set.MaterialLayers:
            material = layer.Material
            material_info = {
                'name': getattr(material, 'Name', 'Unnamed Material'),
                'description': getattr(material, 'Description', 'No description'),
                'thickness': str(layer.LayerThickness) if hasattr(layer, 'LayerThickness') else 'Unknown thickness',
                'layerSetName': layer_set_name,
                'type': 'IfcMaterialLayer'
            }
            materials_info.append(material_info)
            
    elif material_association.is_a("IfcMaterial"):
        # Handle simple IfcMaterial
        material_info = {
            'name': getattr(material_association, 'Name', 'Unnamed Material'),
            'description': getattr(material_association, 'Description', 'No description'),
            'type': 'IfcMaterial'
        }
        materials_info.append(material_info)
        
    elif material_association.is_a("IfcMaterialList"):
        # Handle IfcMaterialList
        for material in material_association.Materials:
            material_info = {
                'name': getattr(material, 'Name', 'Unnamed Material'),
                'description': getattr(material, 'Description', 'No description'),
                'type': 'IfcMaterialList'
            }
            materials_info.append(material_info)
            
    return materials_info
