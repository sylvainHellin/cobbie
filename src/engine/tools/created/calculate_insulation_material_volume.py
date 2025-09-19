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
    
    Note: Results are estimates and should be used for rough quantity assessment only.
    Actual insulation volumes may vary significantly from these estimates.
    For procurement and cost estimation, physical verification is recommended.
    
    Assumptions:
    - For layered constructions, the insulation material is represented as a layer with defined thickness
    - For elements with a single material that is the insulation material, the total volume is returned
    - For other material representation types, thickness cannot be determined
    
    Args:
        element: IfcElement entity (wall, slab, etc.)
        insulation_material: IfcMaterial entity representing the insulation material
        
    Returns:
        float: Estimated volume of insulation material in cubic meters (with inherent uncertainty)
        
    Raises:
        ValueError: If the insulation material is not found in the element's construction
        ValueError: If the thickness of the insulation material cannot be determined
        ValueError: If geometry cannot be created for the element and no fallback is available
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
            raise ValueError(f"Cannot determine thickness of insulation material {insulation_material.Name} in IfcMaterialConstituentSet for element {element.GlobalId}. Estimation not possible.")
                
    elif material_representation.is_a("IfcMaterialProfileSet"):
        # For profile sets, we can't determine layer thickness
        profiles = material_representation.MaterialProfiles
        insulation_found = False
        for profile in profiles or []:
            if profile.Material == insulation_material:
                insulation_found = True
                break
        if insulation_found:
            raise ValueError(f"Cannot determine thickness of insulation material {insulation_material.Name} in IfcMaterialProfileSet for element {element.GlobalId}. Estimation not possible.")
                
    elif material_representation == insulation_material:
        # Element has only one material which is the insulation material
        # In this case, we calculate the total volume of the element
        settings = ifcopenshell.geom.settings()
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            geometry = shape.geometry
            volume = ifcopenshell.util.shape.get_volume(geometry)
            # Return the calculated volume but note that it's an estimate
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
    geometry = None
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        geometry = shape.geometry
    except Exception as e:
        # If geometry creation fails, we'll try to get area from properties if available
        pass
    
    # Calculate the appropriate surface area based on element type
    area = None
    if geometry:
        try:
            if element.is_a("IfcWall") or element.is_a("IfcWallStandardCase"):
                # For walls, calculate the side area (elevation area)
                area = ifcopenshell.util.shape.get_side_area(geometry, axis="Y")
            elif element.is_a("IfcSlab"):
                # For slabs, calculate the footprint area
                area = ifcopenshell.util.shape.get_footprint_area(geometry, axis="Z")
            elif element.is_a("IfcRoof"):
                # For roofs, calculate the footprint area
                area = ifcopenshell.util.shape.get_footprint_area(geometry, axis="Z")
            else:
                # For other elements, calculate total surface area
                area = ifcopenshell.util.shape.get_area(geometry)
        except Exception as e:
            # If area calculation from geometry fails, continue to fallback
            pass
    
    # If we still don't have an area, try to get it from properties
    if area is None:
        # Try to get area from BaseQuantities
        for rel in element.IsDefinedBy:
            if rel.is_a("IfcRelDefinesByProperties"):
                prop_set = rel.RelatingPropertyDefinition
                if prop_set.is_a("IfcElementQuantity"):
                    for quantity in prop_set.Quantities:
                        if quantity.is_a("IfcQuantityArea") and "Area" in quantity.Name:
                            area = quantity.AreaValue
                            break
                if area is not None:
                    break
        
        # If still no area, try to calculate from dimensions for simple shapes
        if area is None and geometry is None:
            # Try to get dimensions from properties
            length = width = height = None
            
            for rel in element.IsDefinedBy:
                if rel.is_a("IfcRelDefinesByProperties"):
                    prop_set = rel.RelatingPropertyDefinition
                    if prop_set.is_a("IfcPropertySet"):
                        for prop in prop_set.HasProperties:
                            if prop.is_a("IfcPropertySingleValue"):
                                if "Length" in prop.Name and prop.NominalValue:
                                    length = prop.NominalValue.wrappedValue
                                elif "Width" in prop.Name and prop.NominalValue:
                                    width = prop.NominalValue.wrappedValue
                                elif "Height" in prop.Name and prop.NominalValue:
                                    height = prop.NominalValue.wrappedValue
            
            # Calculate area based on element type and available dimensions
            if element.is_a("IfcWall") and length and height:
                area = length * height
            elif element.is_a("IfcSlab") and length and width:
                area = length * width
            elif element.is_a("IfcRoof") and length and width:
                area = length * width
    
    # If we still can't determine area, raise an error
    if area is None:
        raise ValueError(f"Could not calculate area for element {element.GlobalId}")
    
    # Calculate volume as thickness * area
    try:
        volume = insulation_thickness * area
        # Return the calculated volume
        # Note: This is still an estimate due to potential variations in actual thickness and area measurements
        return volume
    except Exception as e:
        raise ValueError(f"Could not calculate volume for element {element.GlobalId}: {str(e)}")