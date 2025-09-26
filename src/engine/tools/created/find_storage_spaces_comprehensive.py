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
    - GSA Space Areas
    
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
    
    # Define storage-related keywords for different types
    storage_keywords = {
        "general": [
            "storage", "store", "closet", "pantry", "locker", "stockroom", 
            "Storage Room", "Equipment Room", "Utility Room"
        ],
        "soiled": ["soiled", "trash", "waste", "laundry"],
        "hazardous": ["hazardous", "flammable", "chemical", "gas", "cleaning"],
        "utility": ["utility", "janitor", "maintenance", "mechanical"]
    }
    
    # Define technical room keywords to exclude (but still include storage rooms)
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
        elif "GSA Space Areas" in psets and "GSA BIM Area" in psets["GSA Space Areas"]:
            space_info["Area"] = psets["GSA Space Areas"]["GSA BIM Area"]
        
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
                # But don't exclude if it's explicitly a storage room
                if not (("Storage Room" in space_info["Category"]) or 
                        ("Storage Room" in str(space_info["OmniClass"])) or
                        (space.Name and "storage" in space.Name.lower())):
                    is_technical_room = True
                    break
        
        # Skip technical rooms that are not storage rooms
        if is_technical_room:
            continue
        
        # Check for storage-related terms in various properties
        is_storage = False
        found_type = None
        
        # Check all property values for storage keywords
        storage_indicators = []
        
        # Check space name
        if space.Name:
            storage_indicators.append(space.Name)
        
        # Check category description
        if space_info["Category"]:
            storage_indicators.append(space_info["Category"])
            
        # Check OmniClass
        if space_info["OmniClass"]:
            storage_indicators.append(space_info["OmniClass"])
            
        # Check all property set values
        for pset_name, pset_dict in psets.items():
            for prop_name, prop_value in pset_dict.items():
                if prop_name != "id" and isinstance(prop_value, str):
                    storage_indicators.append(prop_value)
        
        # Check for storage indicators
        for indicator in storage_indicators:
            # Check each storage type
            for storage_type, keywords in storage_keywords.items():
                # If specific storage types are requested, only check those
                if storage_types is None or storage_type in storage_types:
                    for keyword in keywords:
                        if keyword.lower() in indicator.lower():
                            is_storage = True
                            found_type = storage_type
                            break
                if is_storage:
                    break
            if is_storage:
                break
        
        # Special case: explicit storage room classifications
        if not is_storage:
            storage_room_indicators = [
                "Storage Room", "Soiled Storage Room Space", 
                "Hazardous Material Storage Space", "Stockroom",
                "Equipment Room", "Utility Room"
            ]
            
            for indicator in storage_room_indicators:
                # Check in category description, OmniClass, and space name
                if (space_info["Category"] and indicator.lower() in space_info["Category"].lower()) or \
                   (space_info["OmniClass"] and indicator.lower() in space_info["OmniClass"].lower()) or \
                   (space.Name and indicator.lower() in space.Name.lower()):
                    is_storage = True
                    # Determine type based on indicator
                    if "soiled" in indicator.lower():
                        found_type = "soiled"
                    elif "hazardous" in indicator.lower():
                        found_type = "hazardous"
                    elif "utility" in indicator.lower() or "janitor" in indicator.lower():
                        found_type = "utility"
                    else:
                        found_type = "general"
                    break
        
        # If we're looking for all storage types or general storage,
        # check for generic storage classifications
        if not is_storage and (storage_types is None or "general" in storage_types):
            # Check for generic storage room classifications
            generic_storage_indicators = [
                "Storage", "Stockroom", "Closet", "Pantry", "Locker"
            ]
            
            for indicator in generic_storage_indicators:
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