import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
from typing import Dict, List, Optional

def calculate_material_volumes(model_path: str, material_filter: Optional[List[str]] = None) -> Dict[str, float]:
    """
    Calculate the volume of each material in the BIM model.

    Args:
        model_path (str): Path to the IFC model file.
        material_filter (Optional[List[str]]): List of material names to filter results (None for all materials).

    Returns:
        Dict[str, float]: Dictionary mapping material names to their calculated volumes in cubic meters.
    """
    model = ifcopenshell.open(model_path)
    settings = ifcopenshell.geom.settings()
    material_volumes = {}

    for element in model.by_type("IfcElement"):
        try:
            materials = ifcopenshell.util.element.get_materials(element)
            if not materials:
                continue

            shape = ifcopenshell.geom.create_shape(settings, element)
            if not shape or not shape.geometry:
                continue

            volume = ifcopenshell.util.shape.get_volume(shape.geometry)

            for material in materials:
                material_name = getattr(material, 'Name', 'Unnamed')
                if material_filter and material_name not in material_filter:
                    continue
                if material_name in material_volumes:
                    material_volumes[material_name] += volume
                else:
                    material_volumes[material_name] = volume
        except Exception as e:
            continue

    return material_volumes