# python packages
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
def get_rooms_with_outdoor_access(model: str = None, depth: int = 1) -> str:
    """Find rooms that have direct access to outdoor spaces.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
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
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
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

if __name__ == "__main__":
    try:
        # Test with depth 1 (doors only)
        print("\nAnalyzing rooms with outdoor door access (depth=1):")
        result_doors = get_rooms_with_outdoor_access(model="arc", depth=1)
        print(result_doors)
        
        # Test with depth 2 (doors and windows)
        print("\nAnalyzing rooms with outdoor door and window access (depth=2):")
        result_full = get_rooms_with_outdoor_access(model="arc", depth=2)
        print(result_full)
        
        # Test with default parameters
        print("\nTesting with default parameters:")
        result_default = get_rooms_with_outdoor_access()
        print(result_default)
        
    except FileNotFoundError as e:
        print(f"Error: Could not find the IFC model file.\nDetails: {e}")
    except Exception as e:
        print(f"An unexpected error occurred:\nDetails: {e}")
