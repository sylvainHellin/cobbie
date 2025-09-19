import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import List, Dict, Any, Optional

def find_storage_spaces_comprehensive(model_path: str, storage_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Find all storage spaces in an IFC model including specific storage types.
    
    This function searches for storage spaces by examining property sets such as:
    - PSet_Revit_Identity Data
    - PSet_Revit_Other
    - PSet_Revit_Dimensions
    
    It looks for storage classifications in:
    - Space Name
    - Category Description
    - OmniClass Table 13 Category
    
    Note: This function is designed for IFC models exported from Revit and uses
    Revit-specific property sets (PSet_Revit_*).
    
    Args:
        model_path (str): Path to the IFC model file
        storage_types (List[str], optional): Specific storage types to search for 
            (e.g., "general", "soiled", "hazardous", "utility"). 
            If None, searches for all storage types.
            Valid options include: "general", "soiled", "hazardous", "utility"
    
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing storage space information:
            - "Name": Space name
            - "GUID": GlobalId of the space
            - "Type": Storage type classification
            - "Category": Category description from PSet_Revit_Other
            - "OmniClass": OmniClass category from PSet_Revit_Identity Data
            - "Area": Area in square meters (from PSet_Revit_Dimensions.Area if available)
            - "Properties": All property sets and their values
    """
    
    # Define storage-related keywords for different types (excluding technical rooms)
    storage_keywords = {
        "general": ["storage", "store", "closet", "pantry", "locker", "stockroom"],
        "soiled": ["soiled"],
        "hazardous": ["hazardous", "flammable", "gas"],
        "utility": ["utility", "janitor"]
    }
    
    # Define technical room keywords to exclude
    technical_room_keywords = [
        "mechanical", "electrical", "equipment", "plant", "boiler", 
        "generator", "server", "telecom", "data", "IT"
    ]
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all IfcSpace entities
    spaces = model.by_type("IfcSpace")
    
    # Find spaces that match storage criteria
    storage_spaces = []
    
    for space in spaces:
        space_info = {
            "Name": space.Name,
            "GUID": space.GlobalId,
            "Type": None,
            "Category": None,
            "OmniClass": None,
            "Area": None,
            "Properties": {}
        }
        
        # Get all property sets for this space
        psets = ifcopenshell.util.element.get_psets(space)
        space_info["Properties"] = psets
        
        # Extract area if available
        if "PSet_Revit_Dimensions" in psets and "Area" in psets["PSet_Revit_Dimensions"]:
            space_info["Area"] = psets["PSet_Revit_Dimensions"]["Area"]
        
        # Extract category and OmniClass information
        if "PSet_Revit_Other" in psets and "Category Description" in psets["PSet_Revit_Other"]:
            space_info["Category"] = psets["PSet_Revit_Other"]["Category Description"]
            
        if "PSet_Revit_Identity Data" in psets and "OmniClass Table 13 Category" in psets["PSet_Revit_Identity Data"]:
            space_info["OmniClass"] = psets["PSet_Revit_Identity Data"]["OmniClass Table 13 Category"]
        
        # Check if this is a technical room that should be excluded
        is_technical_room = False
        for keyword in technical_room_keywords:
            # Check in category description, OmniClass, and space name
            if (space_info["Category"] and keyword.lower() in space_info["Category"].lower()) or \
               (space_info["OmniClass"] and keyword.lower() in space_info["OmniClass"].lower()) or \
               (space.Name and keyword.lower() in space.Name.lower()):
                is_technical_room = True
                break
        
        # Skip technical rooms
        if is_technical_room:
            continue
        
        # Check for storage-related terms in various properties
        is_storage = False
        found_type = None
        
        # Check all property values for storage keywords
        for pset_name, pset_dict in psets.items():
            for prop_name, prop_value in pset_dict.items():
                if prop_name != "id" and isinstance(prop_value, str):
                    # Check each storage type
                    for storage_type, keywords in storage_keywords.items():
                        # If specific storage types are requested, only check those
                        if storage_types is None or storage_type in storage_types:
                            for keyword in keywords:
                                if keyword.lower() in prop_value.lower():
                                    is_storage = True
                                    found_type = storage_type
                                    break
                        if is_storage:
                            break
                if is_storage:
                    break
            if is_storage:
                break
        
        # Also check the space name itself
        if space.Name and not is_storage:
            for storage_type, keywords in storage_keywords.items():
                # If specific storage types are requested, only check those
                if storage_types is None or storage_type in storage_types:
                    for keyword in keywords:
                        if keyword.lower() in space.Name.lower():
                            is_storage = True
                            found_type = storage_type
                            break
                if is_storage:
                    break
        
        # Special case: if we're looking for all storage types or general storage,
        # check for generic storage classifications
        if not is_storage and (storage_types is None or "general" in storage_types):
            # Check for generic storage room classifications
            storage_room_indicators = [
                "Storage Room", "Soiled Storage Room Space", 
                "Hazardous Material Storage Space", "Stockroom"
            ]
            
            for indicator in storage_room_indicators:
                # Check in category description, OmniClass, and space name
                if (space_info["Category"] and indicator.lower() in space_info["Category"].lower()) or \
                   (space_info["OmniClass"] and indicator.lower() in space_info["OmniClass"].lower()) or \
                   (space.Name and indicator.lower() in space.Name.lower()):
                    is_storage = True
                    found_type = "general"
                    break
        
        if is_storage:
            space_info["Type"] = found_type if found_type else "general"
            storage_spaces.append(space_info)
    
    return storage_spaces