# python packages
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell

def get_door_dimensions(model: str = None, door_id: str = None, door_name: str = None) -> str:
    """Gets the overall width and height of doors from an IFC model.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        door_id (str, optional): ID or GlobalId of specific door.
            Can be any of:
            - GlobalId (e.g., "1s1jVhK8z0pgKYcr9jt781")
            - Element ID (e.g., "1234") 
        door_name (str, optional): Name of the door (e.g., "Door-001")
        If both door_id and door_name are None, returns first door found.
            
    Returns:
        str: JSON string containing door dimensions in meters (with 3 decimal places).
        If door_id or door_name is specified, returns single door data:
            {
                "door_name": "Door-001",
                "door_guid": "1s1jVhK8z0pgKYcr9jt781",
                "overall_width": "1.000",  # or "unknown" if not found
                "overall_height": "2.200"  # or "unknown" if not found
            }
        If no identifier is specified, returns list of all doors:
            [
                {
                    "door_name": "Door-001",
                    "door_guid": "1s1jVhK8z0pgKYcr9jt781",
                    "overall_width": "1.000",
                    "overall_height": "2.200"
                },
                ...
            ]
    """
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    doors = ifc_model.by_type("IfcDoor")
    
    # Function to get dimensions for a single door
    def get_single_door_data(door):
        return {
            "door_name": getattr(door, 'Name', str(door.id())),
            "door_guid": door.GlobalId,
            "overall_width": f"{float(door.OverallWidth):.3f}" if hasattr(door, 'OverallWidth') else "unknown",
            "overall_height": f"{float(door.OverallHeight):.3f}" if hasattr(door, 'OverallHeight') else "unknown"
        }
    
    # If specific door requested
    if door_id or door_name:
        target_door = None
        if door_id:
            target_door = next((door for door in doors 
                              if door_id in (door.GlobalId, door.id())), None)
        elif door_name:
            target_door = next((door for door in doors 
                              if door_name == getattr(door, 'Name', '')), None)
        
        if not target_door:
            identifier = door_id if door_id else door_name
            return f"No door found with identifier: {identifier}"
        
        return json.dumps(get_single_door_data(target_door), indent=2)
    
    # If no specific door requested, return all doors
    all_doors_data = [get_single_door_data(door) for door in doors]
    return json.dumps(all_doors_data, indent=2)

#%%
if __name__ == "__main__":
    # Test with no parameters (first door)
    print("\nTesting with no parameters (all doors):")
    print(get_door_dimensions(model="arc"))
    
    # Test with a door ID (you may need to update this ID for your model)
    print("\nTesting with a specific door ID:")
    print(get_door_dimensions(model="arc", door_id="1hOSvn6df7F8_7GcBWlRGQ"))
    
    # Test with a door name (you may need to update this name for your model)
    print("\nTesting with a door name:")
    print(get_door_dimensions(model="arc", door_name="M_Single-Glass 1:0813 x 2420mm:0813 x 2420mm:171975"))
    
    # Test with an invalid ID
    print("\nTesting with an invalid door ID:")
    print(get_door_dimensions(model="arc", door_id="invalid_id")) 
# %%
