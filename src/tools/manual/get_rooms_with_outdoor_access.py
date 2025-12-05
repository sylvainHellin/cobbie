# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import json

def get_rooms_with_outdoor_access(model_path: str, depth: int = 1) -> str:
    """Find rooms that have direct access to outdoor spaces.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        depth (int): Detail level for the output (1 or 2).
                    1: Only rooms with exterior doors
                    2: All rooms with exterior access (doors and/or windows)
    
    Returns:
        str: A JSON string containing:
            - rooms_with_doors: List of rooms that have exterior doors
            - rooms_with_windows_only: List of rooms that have exterior windows but no doors
              (only if depth == 2)
            - summary:
                - total_rooms_with_doors: Number of rooms with exterior doors
                - total_rooms_with_windows_only: Number of rooms with only exterior windows
    """
    ifc_model = ifcopenshell.open(model_path)
    
    # Initialize results dictionaries
    rooms_with_doors = {}
    rooms_with_windows = {}
    
    # Get all spaces (rooms)
    spaces = ifc_model.by_type("IfcSpace")
    
    # Helper function to check if an element is exterior
    def is_exterior_element(element):
        if not element:
            return False
            
        # Check property sets for IsExternal property
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Common property set names that might contain the IsExternal property
        external_property_sets = [
            "Pset_DoorCommon",
            "Pset_WindowCommon",
            "Pset_WallCommon"
        ]
        
        for pset_name in external_property_sets:
            if pset_name in psets and psets[pset_name].get("IsExternal", False):
                return True
        
        return False
    
    # Iterate through spaces to check their boundaries
    for space in spaces:
        # Get space boundaries
        space_boundaries = ifc_model.get_inverse(space)
        has_door = False
        has_window = False
        
        for rel in space_boundaries:
            if rel.is_a("IfcRelSpaceBoundary"):
                building_element = rel.RelatedBuildingElement
                
                if building_element and is_exterior_element(building_element):
                    if building_element.is_a("IfcDoor"):
                        has_door = True
                    elif building_element.is_a("IfcWindow"):
                        has_window = True
        
        room_name = space.Name or f"Space {space.GlobalId}"
        if has_door:
            rooms_with_doors[room_name] = space.GlobalId
        if has_window:
            rooms_with_windows[room_name] = space.GlobalId
    
    # Prepare the output dictionary with clearer structure
    result = {
        "summary": {
            "total_rooms_with_doors": len(rooms_with_doors),
            "total_rooms_with_windows_only": len([room for room in rooms_with_windows if room not in rooms_with_doors])
        }
    }
    
    if depth >= 1:
        result["rooms_with_doors"] = [
            {"name": room_name, "guid": global_id}
            for room_name, global_id in sorted(rooms_with_doors.items())
        ]
    
    if depth == 2:
        result["rooms_with_windows_only"] = [
            {"name": room_name, "guid": global_id}
            for room_name, global_id in sorted(rooms_with_windows.items())
            if room_name not in rooms_with_doors
        ]

    return json.dumps(result, indent=2)
