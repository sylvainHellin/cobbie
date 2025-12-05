# ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
import json

# Define keywords for spaces to exclude (case-insensitive)
EXCLUDED_KEYWORDS = [
    # Circulation
    "corridor",
    "circulation",
    "stair",
    "elevator",
    "lift",
    "shaft",
    "vestibule",
    "hallway",
    "passage",
    "entrance",
    "exit",
    "escalator",
    
    # Sanitary
    "toilet",
    "wc",
    "bathroom",
    "sanitary",
    "shower",
    "restroom",
    "changing",
    "locker",
    
    # Building Services
    "mechanical",
    "electrical",
    "storage",
    "closet",
    "technical",
    "service",
    "equipment",
    "utility",
    "trash",
    "parking",
    "garage",
    "plant room",
    "boiler",
    "hvac",
    "server",
    "telecom",
    "it room",
    "switchboard",
    "transformer",
    "meter",
    
    # Additional Support Spaces
    "duct",
    "riser",
    "void",
    "plenum",
    "chase",
    "janitor",
    "cleaning",
    "maintenance",
    "loading",
    "dock",
    "waste",
    "recycling",
    "mail room",
    "security",
    
    # Building Envelope & Structure
    "roof",
    "rooftop",
    "terrace",
    "balcony",
    "foundation",
    "basement",
    "crawl space",
    "attic",
    "cavity",
    "wall void",
    "interstitial",
    "soffit",
    "facade",
    "exterior",
    "outdoor",
    "outside",
]

def calculate_usable_floor_area(model_path: str, depth: int = 1,
                              exclude_room_name_contains: list[str] | None = None,
                              only_include_room_name_contains: list[str] | None = None,
                              use_default_exclusions: bool = True):
    """Calculate the Usable Floor Area (UFA) of a building from an IFC model.

    This function calculates the UFA by analyzing IfcSpace elements in the model, excluding spaces that are
    typically not considered usable (like corridors, mechanical rooms, etc.) based on their names and properties.
    The calculation can be customized through various parameters to include or exclude specific spaces.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        depth (int, optional): The level of detail in the results. Defaults to 1.
            - 0: Returns only the total UFA
            - 1: Returns UFA and lists of included/excluded spaces
            - 2: Returns UFA and detailed information for each space
        exclude_room_name_contains (list[str], optional): List of strings to identify spaces to exclude.
            If a space's name or long name contains any of these strings, it will be excluded.
        only_include_room_name_contains (list[str], optional): List of strings to identify spaces to include.
            If provided, only spaces whose name or long name contains any of these strings will be included.
        use_default_exclusions (bool, optional): Whether to use the predefined list of excluded space types
            (corridors, mechanical rooms, etc.). Defaults to True.

    Returns:
        str: A JSON string containing the results with the following structure:
            - For depth=0: {"UFA": float}
            - For depth=1: {
                "UFA": float,
                "included_spaces": {long_name: [space_names]},
                "excluded_spaces": {long_name: [space_names]}
              }
            - For depth=2: {
                "UFA": float,
                "spaces": [{
                    "name": str,
                    "long_name": str,
                    "area": float
                }]
              }

    Notes:
        - Areas are calculated using either the predefined NetFloorArea property or by computing
          the geometric footprint if the property is not available.
        - The function uses case-insensitive string matching for space names.
        - Spaces marked with IsUsable=False in their Pset_SpaceCommon are automatically excluded.
        - All area values in the output are rounded to 2 decimal places.
    """
    ifc_model = ifcopenshell.open(model_path)
    
    # Get all spaces in the building
    spaces = ifc_model.by_type("IfcSpace")
    
    # Initialize exclude and include lists if None
    exclude_room_name_contains = exclude_room_name_contains or []
    only_include_room_name_contains = only_include_room_name_contains or []
    
    # Convert all keywords to lowercase for case-insensitive comparison
    exclude_room_name_contains = [exclude_str.lower() for exclude_str in exclude_room_name_contains]
    only_include_room_name_contains = [include_str.lower() for include_str in only_include_room_name_contains]
    
    total_area = 0
    space_details = []
    included_spaces = {}  # Dictionary with long_name as key, list of names as value
    excluded_spaces = {}  # Dictionary with long_name as key, list of names as value
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)  # Use world coordinates for accurate areas
    
    for space in spaces:
        # Get space long name (or name if long name not available)
        long_name = (space.LongName if hasattr(space, "LongName") and space.LongName else 
                    (space.Name if hasattr(space, "Name") and space.Name else ""))
        name = space.Name if hasattr(space, "Name") and space.Name else f"Space_{space.id()}"
        
        # Convert names to lowercase for comparison
        long_name_lower = long_name.lower()
        name_lower = name.lower()
        
        # Check if space should be excluded
        should_exclude = False
        
        # If only_include_room_name_contains is provided, it takes precedence over everything else
        if only_include_room_name_contains:
            if not any(include_str in name_lower or include_str in long_name_lower 
                      for include_str in only_include_room_name_contains):
                should_exclude = True
            # If the space matches the inclusion list, don't exclude it regardless of other criteria
            else:
                should_exclude = False
                
        # Only check other exclusion criteria if we haven't matched an inclusion pattern
        elif not should_exclude:
            # Only check default exclusions if use_default_exclusions is True
            if use_default_exclusions:
                if any(keyword in long_name_lower or keyword in name_lower for keyword in EXCLUDED_KEYWORDS):
                    should_exclude = True
            
            # Check if any exclude string is contained in either name or long name
            if any(exclude_str in name_lower or exclude_str in long_name_lower 
                   for exclude_str in exclude_room_name_contains):
                should_exclude = True
            
            # Check if space is marked as non-usable
            psets = ifcopenshell.util.element.get_psets(space)
            if psets.get("Pset_SpaceCommon", {}).get("IsUsable", True) == False:
                should_exclude = True
        
        if should_exclude:
            if long_name not in excluded_spaces:
                excluded_spaces[long_name] = []
            excluded_spaces[long_name].append(name)
            continue
        
        try:
            # Try to get the defined net floor area first
            quantities = ifcopenshell.util.element.get_psets(space).get("Qto_SpaceBaseQuantities")
            if quantities and "NetFloorArea" in quantities:
                area = float(quantities["NetFloorArea"])
            else:
                # Calculate the area if not defined
                shape = ifcopenshell.geom.create_shape(settings, space)
                geometry = shape.geometry()
                area = ifcopenshell.util.shape.get_footprint_area(geometry, axis='Z')
            
            total_area += area
            
            # Add to included spaces
            if long_name not in included_spaces:
                included_spaces[long_name] = []
            included_spaces[long_name].append(name)
            
            # If depth=2, collect space details
            if depth == 2:
                space_details.append({
                    "name": name,
                    "long_name": long_name,
                    "area": round(area, 2),
                })
            
        except Exception as e:
            print(f"Warning: Could not process space {space.id()}: {e}")
            if long_name not in excluded_spaces:
                excluded_spaces[long_name] = []
            excluded_spaces[long_name].append(name)
    
    # Prepare result based on depth
    result = {
        "UFA": round(total_area, 2)
    }
    
    if depth == 1:
        # Sort the dictionaries by long_name
        result["included_spaces"] = dict(sorted(included_spaces.items()))
        result["excluded_spaces"] = dict(sorted(excluded_spaces.items()))
    elif depth == 2:
        # Sort spaces by area (descending) for better readability
        space_details.sort(key=lambda x: x["area"], reverse=True)
        result["included_spaces"] = space_details
        
        # Add excluded spaces with area 0 since they were not calculated
        excluded_space_details = []
        for long_name, names in excluded_spaces.items():
            for name in names:
                excluded_space_details.append({
                    "name": name,
                    "long_name": long_name,
                })
        # Sort excluded spaces by name for consistency
        excluded_space_details.sort(key=lambda x: x["name"])
        result["excluded_spaces"] = excluded_space_details

    return json.dumps(result, indent=2)

