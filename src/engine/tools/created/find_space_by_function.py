
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

def find_space_by_function(model: ifcopenshell.file, keywords: str, building_storey: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Find spaces in an IFC model based on functional descriptions or keywords.
    
    This function searches across space names, numbers, and property sets to find spaces
    that match the given keywords. It handles partial matches and case-insensitive search.
    Results can be filtered by building storey/level.
    
    The function addresses issues with rigid search logic by:
    - Searching across all property set values, not just space names
    - Handling partial matches (e.g., finding "TECH. OFFICE" when searching for "tech office")
    - Supporting multi-word keyword searches
    - Allowing optional building storey filtering
    
    Args:
        model (ifcopenshell.file): The IFC model to search in
        keywords (str): Keywords to search for (e.g., "tech office")
        building_storey (Optional[str]): Optional building storey name to filter results
        
    Returns:
        List[Dict[str, Any]]: List of matching spaces with their information including:
            - global_id: Space GlobalId
            - name: Space name
            - number: Space number
            - description: Space description
            - building_storey: Associated building storey
            - area: Space area (if available, typically from PSet_Revit_Dimensions)
            - volume: Space volume (if available, typically from PSet_Revit_Dimensions)
            - properties: All property sets of the space
    
    Example:
        >>> model = ifcopenshell.open("model.ifc")
        >>> spaces = find_space_by_function(model, "waiting room", "First Floor")
        >>> print(spaces[0]['name'])
        'CENTRAL WAITING'
        
        >>> # This will find spaces like "TECH. OFFICE" that previous rigid search missed
        >>> tech_spaces = find_space_by_function(model, "tech office")
    """
    # Normalize keywords for case-insensitive search
    keywords_lower = keywords.lower()
    
    # Get all spaces in the model
    all_spaces = model.by_type("IfcSpace")
    
    matching_spaces = []
    
    for space in all_spaces:
        # Get space basic information
        space_info = {
            "global_id": space.GlobalId,
            "name": space.Name or "",
            "number": "",
            "description": space.Description or "",
            "building_storey": "",
            "area": None,
            "volume": None,
            "properties": {}
        }
        
        # Get building storey information
        # First try the ContainedInStructure relationship
        if hasattr(space, 'ContainedInStructure') and space.ContainedInStructure:
            for rel in space.ContainedInStructure:
                if rel.RelatingStructure.is_a("IfcBuildingStorey"):
                    space_info["building_storey"] = rel.RelatingStructure.Name or ""
                    break
        
        # If that didn't work, try getting it from PSet_Revit_Constraints
        if not space_info["building_storey"]:
            properties = ifcopenshell.util.element.get_psets(space)
            if "PSet_Revit_Constraints" in properties:
                constraints = properties["PSet_Revit_Constraints"]
                if "Level" in constraints:
                    space_info["building_storey"] = constraints["Level"]
        else:
            # Still get properties for later use
            properties = ifcopenshell.util.element.get_psets(space)
        
        space_info["properties"] = properties
        
        # Extract number and area/volume from properties if available
        if "PSet_Revit_Identity Data" in properties:
            identity_data = properties["PSet_Revit_Identity Data"]
            if "Number" in identity_data:
                space_info["number"] = identity_data["Number"]
        
        if "PSet_Revit_Dimensions" in properties:
            dimensions = properties["PSet_Revit_Dimensions"]
            if "Area" in dimensions:
                space_info["area"] = dimensions["Area"]
            if "Volume" in dimensions:
                space_info["volume"] = dimensions["Volume"]
        
        # Check if this space matches our search criteria
        search_fields = [
            space_info["name"],
            space_info["number"],
            space_info["description"],
            space_info["building_storey"]
        ]
        
        # Add property set values to search fields
        for pset_name, pset_dict in properties.items():
            for prop_name, prop_value in pset_dict.items():
                if prop_name != "id":  # Skip the id field
                    search_fields.append(str(prop_value))
        
        # Combine all search fields into one string for matching
        combined_text = " ".join(search_fields).lower()
        
        # Check if all keywords are present (supporting multi-word searches like "tech office")
        keyword_matches = True
        for keyword in keywords_lower.split():
            if keyword not in combined_text:
                keyword_matches = False
                break
        
        # Check if building storey filter matches (if specified)
        storey_matches = True
        if building_storey and building_storey.lower() not in space_info["building_storey"].lower():
            storey_matches = False
        
        # If both keyword and storey filters match, add to results
        if keyword_matches and storey_matches:
            matching_spaces.append(space_info)
    
    return matching_spaces
