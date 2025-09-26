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


def get_element_property_summary(model_path: str, element_guid: str, property_types: List[str] = None) -> Dict:
    """
    Retrieve key properties of building elements in a single call.
    
    This function provides a consolidated way to retrieve commonly requested properties of building elements
    from an IFC model. It focuses on the most frequently requested information: dimensions, fire ratings,
    material properties, and other common attributes.
    
    Args:
        model_path (str): Path to the IFC model file
        element_guid (str): GlobalId of the element to retrieve information for
        property_types (List[str], optional): Specific types of properties to retrieve. 
            Defaults to all. Options include:
            - "dimensions" (width, height, thickness, area, volume)
            - "fire_rating" 
            - "materials"
            - "structural_type"
            - "construction" (material layers, etc.)
            
    Returns:
        Dict: A dictionary containing requested property information in a structured format.
              For each property type requested, returns relevant values with clear labels.
              Includes source information (which property set each value came from) when applicable.
              
    Note:
        This function works with IFC models from various authoring software. Property set names
        and property names may vary depending on the software used to create the IFC model.
        Common property sets like Pset_BuildingElementCommon, Pset_Construction, etc. are checked.
    """
    # Default to all property types if none specified
    if property_types is None:
        property_types = ["dimensions", "fire_rating", "materials", "structural_type", "construction"]
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Find the element by its GlobalId
    element = model.by_guid(element_guid)
    if not element:
        raise ValueError(f"No element found with GlobalId: {element_guid}")
    
    # Initialize result dictionary
    result = {
        "element_type": element.is_a(),
        "element_guid": element_guid,
        "element_name": getattr(element, "Name", None),
        "properties": {}
    }
    
    # Get all property sets for the element
    psets = ifcopenshell.util.element.get_psets(element)
    
    # Extract dimensions if requested
    if "dimensions" in property_types:
        dimensions = {}
        
        # Look for dimensional properties in all property sets
        for pset_name, pset_data in psets.items():
            for prop_name, prop_value in pset_data.items():
                # Skip the 'id' key which is metadata, not a property
                if prop_name != 'id' and any(keyword in prop_name.lower() for keyword in 
                                           ['width', 'height', 'thickness', 'area', 'volume', 
                                            'length', 'depth', 'diameter', 'span']):
                    dimensions[f"{pset_name}.{prop_name}"] = prop_value
        
        # Also check for dimensions in the element's geometry
        try:
            # Try to get shape representation for geometric properties
            if hasattr(element, 'Representation') and element.Representation:
                # This would require more complex geometry processing
                # For now, we'll just note that geometry-based dimensions are available
                dimensions["geometry_available"] = True
        except:
            pass
            
        result["properties"]["dimensions"] = dimensions
    
    # Extract fire rating if requested
    if "fire_rating" in property_types:
        fire_rating = {}
        
        # Look for fire rating properties in all property sets
        for pset_name, pset_data in psets.items():
            for prop_name, prop_value in pset_data.items():
                # Skip the 'id' key which is metadata, not a property
                if prop_name != 'id' and 'fire' in prop_name.lower() and 'rating' in prop_name.lower():
                    fire_rating[f"{pset_name}.{prop_name}"] = prop_value
                    break
            if fire_rating:
                break
                
        # If not found in property sets, check other common locations
        if not fire_rating:
            for pset_name, pset_data in psets.items():
                for prop_name, prop_value in pset_data.items():
                    # Skip the 'id' key which is metadata, not a property
                    if prop_name != 'id' and ('fire' in prop_name.lower() or 'rating' in prop_name.lower()):
                        fire_rating[f"{pset_name}.{prop_name}"] = prop_value
                        
        result["properties"]["fire_rating"] = fire_rating
    
    # Extract materials if requested
    if "materials" in property_types:
        materials_info = {}
        
        # Get materials using IfcOpenShell utility
        materials = ifcopenshell.util.element.get_materials(element)
        if materials:
            material_list = []
            for mat in materials:
                material_dict = {
                    "name": getattr(mat, "Name", None),
                    "description": getattr(mat, "Description", None)
                }
                # Try to get material properties if available
                mat_psets = ifcopenshell.util.element.get_psets(mat)
                if mat_psets:
                    material_dict["properties"] = mat_psets
                material_list.append(material_dict)
            materials_info["materials"] = material_list
        else:
            # If no materials found via get_materials, check in element's property sets
            material_properties = {}
            for pset_name, pset_data in psets.items():
                if 'material' in pset_name.lower():
                    for prop_name, prop_value in pset_data.items():
                        if prop_name != 'id':
                            material_properties[f"{pset_name}.{prop_name}"] = prop_value
            if material_properties:
                materials_info["material_properties"] = material_properties
                
        result["properties"]["materials"] = materials_info
    
    # Extract structural type if requested
    if "structural_type" in property_types:
        structural_info = {}
        
        # Look for structural properties in all property sets
        for pset_name, pset_data in psets.items():
            for prop_name, prop_value in pset_data.items():
                # Skip the 'id' key which is metadata, not a property
                if prop_name != 'id' and any(keyword in prop_name.lower() for keyword in 
                                           ['struct', 'load', 'bearing', 'support', 'anchor']):
                    structural_info[f"{pset_name}.{prop_name}"] = prop_value
                    
        result["properties"]["structural_type"] = structural_info
    
    # Extract construction information if requested
    if "construction" in property_types:
        construction_info = {}
        
        # Look for construction-related properties in all property sets
        for pset_name, pset_data in psets.items():
            for prop_name, prop_value in pset_data.items():
                # Skip the 'id' key which is metadata, not a property
                if prop_name != 'id' and any(keyword in pset_name.lower() for keyword in 
                                           ['constr', 'layer', 'assembly', 'build']):
                    if "layers" not in construction_info:
                        construction_info["layers"] = {}
                    construction_info["layers"][f"{pset_name}.{prop_name}"] = prop_value
                    
        result["properties"]["construction"] = construction_info
    
    return result