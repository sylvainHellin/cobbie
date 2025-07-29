
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

def get_material_general_info(material_name: str) -> Dict[str, Any]:
    """
    Provides general knowledge about building materials when specific properties 
    are not available in the IFC model.
    
    Args:
        material_name (str): The name of the material to get information for
        
    Returns:
        Dict[str, Any]: A dictionary containing general information about the material
    """
    # Database of common building materials and their properties
    material_database = {
        "EPDM": {
            "name": "Ethylene Propylene Diene Monomer (EPDM)",
            "type": "Roofing Membrane",
            "typical_lifespan": "25-30 years",
            "properties": {
                "waterproof": True,
                "UV_resistant": True,
                "flexible": True,
                "chemical_resistant": True
            },
            "description": "Synthetic rubber roofing membrane commonly used for flat roofs"
        },
        "EPDM membrane": {
            "name": "Ethylene Propylene Diene Monomer (EPDM) Membrane",
            "type": "Roofing Membrane",
            "typical_lifespan": "25-30 years",
            "properties": {
                "waterproof": True,
                "UV_resistant": True,
                "flexible": True,
                "chemical_resistant": True
            },
            "description": "Synthetic rubber roofing membrane commonly used for flat roofs"
        },
        "Concrete": {
            "name": "Concrete",
            "type": "Structural Material",
            "typical_lifespan": "50-100 years",
            "properties": {
                "compressive_strength": "High",
                "fire_resistant": True,
                "durable": True
            },
            "description": "Composite material composed of fine and coarse aggregate bonded with fluid cement"
        },
        "Steel": {
            "name": "Steel",
            "type": "Structural Material",
            "typical_lifespan": "50-100 years (with protection)",
            "properties": {
                "high_strength": True,
                "ductile": True,
                "corrosion_resistant": False
            },
            "description": "Alloy made from iron and carbon, widely used in construction"
        },
        "Brick": {
            "name": "Brick",
            "type": "Masonry Material",
            "typical_lifespan": "100+ years",
            "properties": {
                "fire_resistant": True,
                "durable": True,
                "low_maintenance": True
            },
            "description": "Clay blocks used for building construction"
        },
        "Wood": {
            "name": "Wood",
            "type": "Structural/Renewable Material",
            "typical_lifespan": "20-100 years (depending on treatment and species)",
            "properties": {
                "renewable": True,
                "insulating": True,
                "biodegradable": True
            },
            "description": "Natural material from trees, used in various construction applications"
        }
    }
    
    # Try to find the material in our database (case insensitive)
    material_info = None
    for key, value in material_database.items():
        if material_name.lower() in key.lower() or key.lower() in material_name.lower():
            material_info = value
            break
    
    # If we didn't find an exact match, try a partial match
    if material_info is None:
        for key, value in material_database.items():
            if material_name.lower() in key.lower() or key.lower() in material_name.lower():
                material_info = value
                break
    
    if material_info is None:
        return {
            "error": f"No general information found for material: {material_name}",
            "suggestion": "Consider expanding the material database or checking the material name spelling"
        }
    
    return material_info
