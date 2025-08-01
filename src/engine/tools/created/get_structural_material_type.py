
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

def get_structural_material_type(ifc_file_path: str, element_guid: str) -> str:
    """
    Identifies the material type of a structural element in an IFC file.
    
    This function is designed to help distinguish between different structural systems
    such as steel frame vs. concrete frame structures by identifying the specific
    material type of structural elements like columns, beams, and other framing members.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_guid (str): GUID of the structural element
        
    Returns:
        str: The material type of the structural element (e.g., 'Steel', 'Concrete', 'Timber')
        
    Raises:
        ValueError: If the element with the specified GUID is not found
        Exception: If no material association is found for the element or if material type cannot be determined
    """
    # Load the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Find the element by GUID
    element = model.by_guid(element_guid)
    if not element:
        raise ValueError(f"Element with GUID {element_guid} not found")
    
    # Check for material associations
    material_associations = model.get_inverse(element)
    material_relations = [rel for rel in material_associations if rel.is_a("IfcRelAssociatesMaterial")]
    
    if not material_relations:
        raise Exception(f"No material association found for element {element_guid}")
    
    # Get the first material relation (typically there's only one)
    material_relation = material_relations[0]
    material = material_relation.RelatingMaterial
    
    # Handle different types of material representations
    if material.is_a("IfcMaterial"):
        return material.Name
    elif material.is_a("IfcMaterialList"):
        # For material lists, return the first material name
        if material.Materials:
            return material.Materials[0].Name
    elif material.is_a("IfcMaterialLayerSetUsage"):
        # For layer sets, return the name of the layer set
        return material.ForLayerSet.LayerSetName
    elif material.is_a("IfcMaterialProfileSetUsage"):
        # For profile sets, return the name of the profile set
        return material.ForProfileSet.ProfileName
    else:
        # For any other material type, try to get a name
        material_name = getattr(material, 'Name', None)
        if material_name:
            return material_name
    
    # If we get here, we couldn't determine the material name
    raise Exception(f"Could not determine material type for element {element_guid}")
