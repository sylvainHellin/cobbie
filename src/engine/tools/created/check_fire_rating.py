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

def check_fire_rating(element: ifcopenshell.entity_instance) -> Dict[str, Any]:
    """
    Check fire rating information for an IFC building element.
    
    This function looks for fire rating properties in common property sets:
    - Standard IFC property sets (Pset_DoorCommon, Pset_WallCommon, etc.) with 'FireRating' property
    - Revit-specific property sets (PSet_Revit_Type_Identity Data) with 'Fire Rating' property
    
    Args:
        element: An IFC element (IfcWall, IfcDoor, IfcSlab, etc.)
        
    Returns:
        A dictionary containing:
        - 'has_fire_rating': Boolean indicating if fire rating information was found
        - 'fire_rating': The fire rating value if found, None otherwise
        - 'source_pset': The name of the property set where the fire rating was found, None if not found
        - 'source_property': The name of the property where the fire rating was found, None if not found
        
    Note:
        This function is designed to work with IFC models that follow standard IFC property set
        conventions and Revit-specific property sets (PSet_Revit_*). For other BIM authoring
        software, additional property set names may need to be added.
    """
    # Get all property sets for the element
    psets = ifcopenshell.util.element.get_psets(element)
    
    # Common property set names that might contain fire rating information
    fire_rating_pset_names = [
        "Pset_DoorCommon",
        "Pset_WallCommon", 
        "Pset_SlabCommon",
        "Pset_RoofCommon",
        "Pset_CoveringCommon",
        "Pset_WindowCommon",
        "Pset_StairCommon",
        "PSet_Revit_Type_Identity Data"  # Revit-specific
    ]
    
    # Common property names for fire ratings
    fire_rating_property_names = [
        "FireRating",      # Standard IFC
        "Fire Rating"      # Revit-specific
    ]
    
    # Search for fire rating properties
    for pset_name, properties in psets.items():
        # Check if this is a property set we're interested in
        if pset_name in fire_rating_pset_names:
            # Look for fire rating properties in this property set
            for property_name in fire_rating_property_names:
                if property_name in properties:
                    fire_rating_value = properties[property_name]
                    # Return the fire rating information
                    return {
                        'has_fire_rating': True,
                        'fire_rating': fire_rating_value,
                        'source_pset': pset_name,
                        'source_property': property_name
                    }
    
    # If no fire rating information was found
    return {
        'has_fire_rating': False,
        'fire_rating': None,
        'source_pset': None,
        'source_property': None
    }