
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *

def get_foundation_material_info(ifc_file_path: str) -> List[Dict[str, Any]]:
    """
    Extract foundation material information from an IFC file.
    
    This function identifies foundation elements (IfcFooting and IfcSlab with PredefinedType.BASESLAB)
    and extracts their associated material properties.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing foundation material information.
                             Each dictionary contains:
                             - element_guid: GlobalId of the foundation element
                             - element_name: Name of the foundation element
                             - element_type: Type of foundation element (IfcFooting or IfcSlab)
                             - materials: List of material dictionaries with properties
    """
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Initialize result list
    foundation_materials = []
    
    # Identify foundation elements
    # 1. IfcFooting elements
    footings = ifc_file.by_type("IfcFooting")
    
    # 2. IfcSlab elements with PredefinedType.BASESLAB
    slabs = ifc_file.by_type("IfcSlab")
    foundation_slabs = [slab for slab in slabs if getattr(slab, 'PredefinedType', None) == 'BASESLAB']
    
    # 3. Additional check for slabs that might be foundations based on name
    potential_foundation_slabs = []
    for slab in slabs:
        name = getattr(slab, 'Name', '') or ''
        description = getattr(slab, 'Description', '') or ''
        if any(keyword in name.lower() or keyword in description.lower() 
               for keyword in ['foundation', 'base slab', 'mat foundation']):
            potential_foundation_slabs.append(slab)
    
    # Combine all foundation elements
    foundation_elements = footings + foundation_slabs + potential_foundation_slabs
    
    # Remove duplicates while preserving order
    seen = set()
    unique_foundation_elements = []
    for element in foundation_elements:
        if element.GlobalId not in seen:
            seen.add(element.GlobalId)
            unique_foundation_elements.append(element)
    
    # Extract material information for each foundation element
    for element in unique_foundation_elements:
        element_info = {
            "element_guid": element.GlobalId,
            "element_name": element.Name if element.Name else "Unnamed",
            "element_type": element.is_a(),
            "materials": []
        }
        
        # Get material associations
        material_relations = [r for r in element.HasAssociations if r.is_a("IfcRelAssociatesMaterial")]
        
        # Extract material information from each association
        for rel in material_relations:
            material = rel.RelatingMaterial
            
            if material.is_a("IfcMaterial"):
                # Simple material
                material_info = {
                    "name": material.Name if material.Name else "Unnamed Material",
                    "type": "IfcMaterial"
                }
                
                # Try to get material properties
                if hasattr(material, 'Category') and material.Category:
                    material_info["category"] = material.Category
                
                element_info["materials"].append(material_info)
                
            elif material.is_a("IfcMaterialLayerSet"):
                # Layered material
                material_info = {
                    "name": material.LayerSetName if material.LayerSetName else "Unnamed Layer Set",
                    "type": "IfcMaterialLayerSet",
                    "layers": []
                }
                
                # Extract information from each layer
                for layer in material.MaterialLayers:
                    layer_info = {
                        "thickness": float(layer.LayerThickness) if layer.LayerThickness else 0.0
                    }
                    
                    if layer.Material:
                        layer_info["material_name"] = layer.Material.Name if layer.Material.Name else "Unnamed Layer Material"
                        if hasattr(layer.Material, 'Category') and layer.Material.Category:
                            layer_info["category"] = layer.Material.Category
                    
                    material_info["layers"].append(layer_info)
                
                element_info["materials"].append(material_info)
            
            elif material.is_a("IfcMaterialList"):
                # List of materials
                material_info = {
                    "name": "Material List",
                    "type": "IfcMaterialList",
                    "materials": []
                }
                
                for mat in material.Materials:
                    mat_info = {
                        "name": mat.Name if mat.Name else "Unnamed Material"
                    }
                    if hasattr(mat, 'Category') and mat.Category:
                        mat_info["category"] = mat.Category
                    material_info["materials"].append(mat_info)
                
                element_info["materials"].append(material_info)
        
        foundation_materials.append(element_info)
    
    return foundation_materials
