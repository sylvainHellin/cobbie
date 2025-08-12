import ifcopenshell
from typing import List, Dict

def get_insulation_materials(ifc_file_path: str) -> List[Dict[str, str]]:
    """
    Identify insulation materials in building elements from IFC models.

    Args:
        ifc_file_path (str): Path to the IFC model file.

    Returns:
        List[Dict[str, str]]: A list of dictionaries containing the building element name, element type, and insulation material name.
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_file_path)

    # List to store the results
    insulation_materials = []

    # Iterate through the IFC entities
    for entity in model.by_type("IfcElement"):
        # Get the element name and type
        element_name = entity.Name if hasattr(entity, "Name") else "Unnamed"
        element_type = entity.is_a()

        # Get the material information
        materials = ifcopenshell.util.element.get_materials(entity)

        # Check if the material is an insulation material
        for material in materials:
            material_name = material.Name if hasattr(material, "Name") else "Unnamed"
            if "insulation" in material_name.lower():
                insulation_materials.append({
                    "element_name": element_name,
                    "element_type": element_type,
                    "insulation_material": material_name
                })

    return insulation_materials