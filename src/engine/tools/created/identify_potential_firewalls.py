import ifcopenshell
import re
from typing import List, Dict, Any, Optional

def identify_potential_firewalls(
    model_path: str, 
    wall_type_patterns: List[str] = None, 
    material_patterns: List[str] = None, 
    location_criteria: Dict = None
) -> List[Dict]:
    """
    Identifies potential firewalls in an IFC model based on construction materials, 
    location, and building code requirements, even without explicit fire rating labels.
    
    This function is designed for IFC models exported from Revit and looks for:
    1. Explicit fire rating properties
    2. Construction materials typically associated with firewalls (CMU, concrete, etc.)
    3. Wall positioning that suggests firewall function (between units, core walls, etc.)
    4. Wall types that typically function as firewalls based on naming conventions
    
    Args:
        model_path (str): Path to the IFC file
        wall_type_patterns (List[str], optional): Patterns to match in wall names/types.
            Defaults to ["fire", "party", "core", "demising", "cmu", "concrete", "masonry"]
        material_patterns (List[str], optional): Patterns to match in material names.
            Defaults to ["cmu", "concrete", "masonry", "gypsum", "steel", "block"]
        location_criteria (Dict, optional): Criteria for identifying wall positioning.
            Can include keys like 'between_units', 'core_wall', 'thickness_threshold'.
            Currently implements basic thickness checking.
            
    Returns:
        List[Dict]: List of potential firewalls with information about each wall including:
            - global_id: The wall's GlobalId
            - name: The wall's name
            - object_type: The wall's object type
            - material_info: Information about the wall's materials
            - property_sets: Dictionary of property sets associated with the wall
            - indicators: List of reasons why this wall was identified as a potential firewall
            - fire_rating: Any explicit fire rating found (if applicable)
    """
    # Set default patterns if not provided
    if wall_type_patterns is None:
        wall_type_patterns = ["fire", "party", "core", "demising", "cmu", "concrete", "masonry"]
    
    if material_patterns is None:
        material_patterns = ["cmu", "concrete", "masonry", "gypsum", "steel", "block"]
    
    if location_criteria is None:
        location_criteria = {}
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all wall elements
    walls = model.by_type("IfcWall")
    
    # List to store potential firewalls
    potential_firewalls = []
    
    # Process each wall
    for wall in walls:
        wall_info = {
            "global_id": wall.GlobalId,
            "name": wall.Name or "N/A",
            "object_type": wall.ObjectType or "N/A",
            "material_info": [],
            "property_sets": {},
            "indicators": [],
            "fire_rating": None
        }
        
        # Check name and object type for firewall indicators
        name_lower = (wall.Name or "").lower()
        object_type_lower = (wall.ObjectType or "").lower()
        
        # Check for associated property sets
        fire_rating_found = False
        if hasattr(wall, "IsDefinedBy"):
            for rel in wall.IsDefinedBy:
                if rel.is_a("IfcRelDefinesByProperties"):
                    prop_set = rel.RelatingPropertyDefinition
                    if prop_set.is_a("IfcPropertySet"):
                        prop_set_name = prop_set.Name
                        if prop_set_name not in wall_info["property_sets"]:
                            wall_info["property_sets"][prop_set_name] = {}
                        for prop in prop_set.HasProperties:
                            if prop.is_a("IfcPropertySingleValue"):
                                wall_info["property_sets"][prop_set_name][prop.Name] = str(prop.NominalValue)
                                
                                # Check for explicit fire rating properties
                                prop_name_lower = prop.Name.lower()
                                if ("fire" in prop_name_lower and "rating" in prop_name_lower) or \
                                   ("fire" in prop_name_lower and "rate" in prop_name_lower) or \
                                   prop_name_lower in ["fire_rating", "firerating"]:
                                    wall_info["fire_rating"] = str(prop.NominalValue)
                                    wall_info["indicators"].append(f"Explicit fire rating: {prop.NominalValue}")
                                    fire_rating_found = True
                                
                                # Check property values for firewall indicators
                                prop_value_lower = str(prop.NominalValue).lower()
                                for pattern in material_patterns:
                                    if pattern in prop_value_lower and ("material" in prop.Name.lower() or 
                                                                       "description" in prop.Name.lower()):
                                        wall_info["indicators"].append(f"Property '{prop.Name}' contains material '{pattern}'")
        
        # Check for material information
        material_indicators = 0
        if hasattr(wall, "HasAssociations"):
            for assoc in wall.HasAssociations:
                if assoc.is_a("IfcRelAssociatesMaterial"):
                    material = assoc.RelatingMaterial
                    if material.is_a("IfcMaterial"):
                        material_info = f"Material: {material.Name}"
                        wall_info["material_info"].append(material_info)
                        
                        # Check material name for firewall indicators
                        material_name_lower = (material.Name or "").lower()
                        for pattern in material_patterns:
                            if pattern in material_name_lower:
                                wall_info["indicators"].append(f"Material name contains '{pattern}'")
                                material_indicators += 1
                                
                    elif material.is_a("IfcMaterialLayerSet"):
                        material_info = f"Material Layer Set: {material.LayerSetName}"
                        wall_info["material_info"].append(material_info)
                        
                        # Check layer set name for firewall indicators
                        layer_set_name_lower = (material.LayerSetName or "").lower()
                        for pattern in material_patterns:
                            if pattern in layer_set_name_lower:
                                wall_info["indicators"].append(f"Layer set name contains '{pattern}'")
                                material_indicators += 1
                                
                        # Check individual layers
                        for layer in material.MaterialLayers:
                            if layer.Material:
                                layer_material_info = f"Layer Material: {layer.Material.Name if layer.Material else 'N/A'}"
                                wall_info["material_info"].append(layer_material_info)
                                
                                # Check layer material name for firewall indicators
                                layer_material_name_lower = (layer.Material.Name or "").lower()
                                for pattern in material_patterns:
                                    if pattern in layer_material_name_lower:
                                        wall_info["indicators"].append(f"Layer material contains '{pattern}'")
                                        material_indicators += 1
                                        
                                # Check layer thickness for firewall indicators
                                if hasattr(layer, "LayerThickness") and location_criteria.get("thickness_threshold"):
                                    if layer.LayerThickness >= location_criteria["thickness_threshold"]:
                                        wall_info["indicators"].append(f"Thick layer ({layer.LayerThickness}m) suggests firewall")
                                        
                    elif material.is_a("IfcMaterialLayerSetUsage"):
                        # Handle IfcMaterialLayerSetUsage
                        layer_set = material.ForLayerSet
                        material_info = f"Material Layer Set Usage: {layer_set.LayerSetName if layer_set.LayerSetName else 'N/A'}"
                        wall_info["material_info"].append(material_info)
                        
                        # Check layer set name for firewall indicators
                        if layer_set.LayerSetName:
                            layer_set_name_lower = layer_set.LayerSetName.lower()
                            for pattern in material_patterns:
                                if pattern in layer_set_name_lower:
                                    wall_info["indicators"].append(f"Layer set usage name contains '{pattern}'")
                                    material_indicators += 1
                                    
                        # Check individual layers
                        if hasattr(layer_set, "MaterialLayers"):
                            for layer in layer_set.MaterialLayers:
                                if layer.Material:
                                    layer_material_info = f"Layer Material: {layer.Material.Name if layer.Material else 'N/A'}"
                                    wall_info["material_info"].append(layer_material_info)
                                    
                                    # Check layer material name for firewall indicators
                                    layer_material_name_lower = (layer.Material.Name or "").lower()
                                    for pattern in material_patterns:
                                        if pattern in layer_material_name_lower:
                                            wall_info["indicators"].append(f"Layer material contains '{pattern}'")
                                            material_indicators += 1
                                            
                                    # Check layer thickness for firewall indicators
                                    if hasattr(layer, "LayerThickness") and location_criteria.get("thickness_threshold"):
                                        if layer.LayerThickness >= location_criteria["thickness_threshold"]:
                                            wall_info["indicators"].append(f"Thick layer ({layer.LayerThickness}m) suggests firewall")
        
        # Check name and object type for firewall indicators (more specific patterns)
        name_indicators = 0
        for pattern in wall_type_patterns:
            if pattern in name_lower or pattern in object_type_lower:
                wall_info["indicators"].append(f"Name/Type contains '{pattern}'")
                name_indicators += 1
        
        # Check for location-based indicators
        location_indicators = 0
        if location_criteria.get("between_units") and ("party" in name_lower or "demising" in name_lower):
            wall_info["indicators"].append("Located between units (party/demising wall)")
            location_indicators += 1
            
        # Only classify as potential firewall if we have strong evidence:
        # Either an explicit fire rating, or multiple indicators (at least 2 name/type + 1 material)
        if fire_rating_found or (name_indicators >= 1 and material_indicators >= 1) or (name_indicators >= 1 and location_indicators >= 1):
            potential_firewalls.append(wall_info)
    
    return potential_firewalls