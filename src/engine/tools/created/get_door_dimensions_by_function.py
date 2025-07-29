
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
import re
from typing import List, Dict, Any

def get_door_dimensions_by_function(ifc_file_path: str, door_function: str, dimension_names: List[str] = None) -> List[Dict[str, Any]]:
    """
    Extract dimensional properties from doors based on their functional role (e.g., "main entrance", "emergency exit", "interior").
    This function intelligently identifies doors by their function through name pattern matching and property analysis,
    then extracts the requested dimensions.

    Parameters:
    - ifc_file_path (str): Path to the IFC file
    - door_function (str): The functional role of the door to search for. Supported values include:
      - "main entrance": Identifies main entrance doors (looks for "main", "entrance", "entry", "lobby" in names, and IsExternal=True)
      - "emergency exit": Identifies emergency exit doors (looks for "emergency", "egress", "exit" in names, and FireRating properties)
      - "interior": Identifies interior doors (IsExternal=False)
      - "exterior": Identifies exterior doors (IsExternal=True)
    - dimension_names (List[str], optional): List of dimension names to extract. Defaults to ['Width', 'Height']. 
      Other common dimensions include 'Area', 'Perimeter'.

    Returns:
    List of dictionaries, each containing:
    - door_name: The door's name
    - door_guid: The door's GlobalId
    - function_match: The identified door function
    - dimensions: Dictionary mapping dimension names to their values
    - source: Indicates whether the value came from 'property', 'name_parsing', or 'calculated'
    - confidence: A score (0-1) indicating the reliability of the door function identification and dimension extraction
    """
    if dimension_names is None:
        dimension_names = ['Width', 'Height']
    
    # Load the IFC model
    model = ifcopenshell.open(ifc_file_path)
    
    # Get all door elements
    doors = model.by_type("IfcDoor")
    
    results = []
    
    # Process each door
    for door in doors:
        # Check if door matches the requested function
        function_match, confidence = _matches_door_function(door, door_function)
        
        if function_match:
            # Extract dimensions
            dimensions, source = _extract_door_dimensions(door, dimension_names)
            
            # Assemble result
            result = {
                "door_name": door.Name if door.Name else "Unnamed Door",
                "door_guid": door.GlobalId,
                "function_match": door_function,
                "dimensions": dimensions,
                "source": source,
                "confidence": confidence
            }
            
            results.append(result)
    
    return results

def _matches_door_function(door, door_function: str) -> tuple:
    """
    Check if a door matches the specified function and return confidence score.
    
    Returns:
        tuple: (bool indicating match, confidence score)
    """
    # Get door properties
    psets = ifcopenshell.util.element.get_psets(door)
    
    # Get IsExternal property if available
    is_external = None
    if "Pset_DoorCommon" in psets:
        is_external = psets["Pset_DoorCommon"].get("IsExternal")
    
    # Get FireRating if available
    fire_rating = None
    if "Pset_DoorCommon" in psets:
        fire_rating = psets["Pset_DoorCommon"].get("FireRating")
    
    # Get door name for keyword matching
    door_name = door.Name.lower() if door.Name else ""
    
    # Check for function match based on door_function parameter
    if door_function == "main entrance":
        # Look for keywords and verify IsExternal=True
        keywords = ["main", "entrance", "entry", "lobby"]
        has_keyword = any(keyword in door_name for keyword in keywords)
        # Must be both external and have keyword
        if has_keyword and is_external is True:
            return True, 0.95
        elif has_keyword and is_external is None:
            return True, 0.7
        else:
            return False, 0.0
    
    elif door_function == "emergency exit":
        # Look for keywords and check for FireRating
        keywords = ["emergency", "egress", "exit"]
        has_keyword = any(keyword in door_name for keyword in keywords)
        # Check if fire rating is meaningful (not just the default "Fire Rating" string)
        has_fire_rating = fire_rating is not None and fire_rating != "" and fire_rating != "Fire Rating"
        
        # Must have both keyword and meaningful fire rating
        if has_keyword and has_fire_rating:
            return True, 0.95
        elif has_keyword:
            return True, 0.7
        elif has_fire_rating:
            return True, 0.6
        else:
            return False, 0.0
    
    elif door_function == "interior":
        # Check that IsExternal=False
        if is_external is False:
            return True, 0.95
        elif is_external is None:
            # If IsExternal is not defined, check if it's not explicitly external
            return True, 0.6
        else:
            return False, 0.0
    
    elif door_function == "exterior":
        # Check that IsExternal=True
        if is_external is True:
            return True, 0.95
        elif is_external is None:
            # If IsExternal is not defined, we can't be certain
            return False, 0.0
        else:
            return False, 0.0
    
    # If door_function is not recognized
    return False, 0.0

def _extract_door_dimensions(door, dimension_names: List[str]) -> tuple:
    """
    Extract dimensions from a door element.
    
    Returns:
        tuple: (dimensions dictionary, source information)
    """
    dimensions = {}
    source = {}
    
    # Get all property sets
    psets = ifcopenshell.util.element.get_psets(door)
    
    # Look for dimensions in property sets
    for dim_name in dimension_names:
        found = False
        
        # Check common property sets for dimensions in order of preference
        property_sets_to_check = [
            "PSet_Revit_Type_Dimensions", 
            "PSet_Revit_Other", 
            "Pset_DoorCommon", 
            "PSet_Revit_Type_Other"
        ]
        
        for pset_name in property_sets_to_check:
            if pset_name in psets and dim_name in psets[pset_name]:
                value = psets[pset_name][dim_name]
                # Special handling for Area which might be a string placeholder
                if dim_name.lower() == "area" and isinstance(value, str):
                    # If it's a string, it's likely a placeholder, so we'll calculate it later
                    pass
                else:
                    dimensions[dim_name] = value
                    source[dim_name] = "property"
                    found = True
                    break
        
        # If not found in properties, try to parse from name
        if not found:
            # Try to extract from door name if it contains dimensions
            door_name = door.Name if door.Name else ""
            # Simple parsing - look for patterns like "0762 x 2032mm"
            pattern = r"(\d+)\s*[xX]\s*(\d+)mm"
            match = re.search(pattern, door_name)
            if match:
                width_mm, height_mm = match.groups()
                if dim_name.lower() == "width":
                    dimensions[dim_name] = float(width_mm) / 1000  # Convert to meters
                    source[dim_name] = "name_parsing"
                    found = True
                elif dim_name.lower() == "height":
                    dimensions[dim_name] = float(height_mm) / 1000  # Convert to meters
                    source[dim_name] = "name_parsing"
                    found = True
        
        # If still not found, set to None
        if not found:
            dimensions[dim_name] = None
            source[dim_name] = "not_found"
    
    # Calculate derived dimensions
    for dim_name in dimension_names:
        if dim_name.lower() == "area" and source[dim_name] == "not_found":
            # Try to calculate area from width and height
            width = dimensions.get("Width")
            height = dimensions.get("Height")
            if width is not None and height is not None and isinstance(width, (int, float)) and isinstance(height, (int, float)):
                dimensions[dim_name] = width * height
                source[dim_name] = "calculated"
    
    return dimensions, source
