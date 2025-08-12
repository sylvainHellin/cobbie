
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
from typing import Union

def calculate_insulation_material_volume(element: ifcopenshell.entity_instance, insulation_material: ifcopenshell.entity_instance) -> float:
    """
    Calculate the volume of insulation material in a building element.
    
    This function extracts the layer thickness for the specified insulation material 
    from the element's construction and multiplies it by the element's surface area.
    
    Assumptions:
    - For layered constructions, the insulation material is represented as a layer with defined thickness
    - For elements with a single material that is the insulation material, the total volume is returned
    - For other material representation types, thickness cannot be determined
    
    Args:
        element: IfcElement entity (wall, slab, etc.)
        insulation_material: IfcMaterial entity representing the insulation material
        
    Returns:
        float: Volume of insulation material in cubic meters
        
    Raises:
        ValueError: If the insulation material is not found in the element's construction
        ValueError: If the thickness of the insulation material cannot be determined
        ValueError: If geometry cannot be created for the element
        ValueError: If area calculations fail
    """
    # Get the material representation of the element
    material_representation = ifcopenshell.util.element.get_material(element)
    
    if not material_representation:
        raise ValueError(f"Element {element.GlobalId} has no material representation")
    
    # Find the insulation material layer and get its thickness
    insulation_thickness = None
    
    # Handle different material representation types
    if material_representation.is_a("IfcMaterialLayerSetUsage"):
        layer_set = material_representation.ForLayerSet
        for layer in layer_set.MaterialLayers:
            if layer.Material == insulation_material:
                insulation_thickness = layer.LayerThickness
                break
                
    elif material_representation.is_a("IfcMaterialLayerSet"):
        for layer in material_representation.MaterialLayers:
            if layer.Material == insulation_material:
                insulation_thickness = layer.LayerThickness
                break
                
    elif material_representation.is_a("IfcMaterialConstituentSet"):
        # For constituent sets, we can't determine layer thickness
        constituents = material_representation.MaterialConstituents
        insulation_found = False
        for constituent in constituents or []:
            if constituent.Material == insulation_material:
                insulation_found = True
                break
        if insulation_found:
            raise ValueError(f"Cannot determine thickness of insulation material {insulation_material.Name} in IfcMaterialConstituentSet for element {element.GlobalId}")
                
    elif material_representation.is_a("IfcMaterialProfileSet"):
        # For profile sets, we can't determine layer thickness
        profiles = material_representation.MaterialProfiles
        insulation_found = False
        for profile in profiles or []:
            if profile.Material == insulation_material:
                insulation_found = True
                break
        if insulation_found:
            raise ValueError(f"Cannot determine thickness of insulation material {insulation_material.Name} in IfcMaterialProfileSet for element {element.GlobalId}")
                
    elif material_representation == insulation_material:
        # Element has only one material which is the insulation material
        # In this case, we calculate the total volume of the element
        settings = ifcopenshell.geom.settings()
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            geometry = shape.geometry
            volume = ifcopenshell.util.shape.get_volume(geometry)
            return volume
        except Exception as e:
            raise ValueError(f"Could not calculate volume for element {element.GlobalId} with single material: {str(e)}")
    
    # If we still haven't found the insulation thickness, check if the material exists at all
    if insulation_thickness is None:
        # Check if the insulation material is associated with the element at all
        all_materials = ifcopenshell.util.element.get_materials(element)
        if insulation_material not in all_materials:
            raise ValueError(f"Insulation material {insulation_material.Name} not found in element {element.GlobalId}'s construction")
        else:
            # Material exists but we can't determine its thickness
            material_type = material_representation.is_a()
            raise ValueError(f"Cannot determine thickness of insulation material {insulation_material.Name} in material representation type {material_type} for element {element.GlobalId}")
    
    # Calculate the geometry for area calculations
    settings = ifcopenshell.geom.settings()
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        geometry = shape.geometry
    except Exception as e:
        raise ValueError(f"Could not create geometry for element {element.GlobalId}: {str(e)}")
    
    # Calculate the appropriate surface area based on element type
    try:
        if element.is_a("IfcWall") or element.is_a("IfcWallStandardCase"):
            # For walls, calculate the side area (elevation area)
            area = ifcopenshell.util.shape.get_side_area(geometry, axis="Y")
        elif element.is_a("IfcSlab"):
            # For slabs, calculate the footprint area
            area = ifcopenshell.util.shape.get_footprint_area(geometry, axis="Z")
        else:
            # For other elements, calculate total surface area
            area = ifcopenshell.util.shape.get_area(geometry)
    except Exception as e:
        raise ValueError(f"Could not calculate area for element {element.GlobalId}: {str(e)}")
    
    # Calculate volume as thickness * area
    try:
        volume = insulation_thickness * area
        return volume
    except Exception as e:
        raise ValueError(f"Could not calculate volume for element {element.GlobalId}: {str(e)}")
