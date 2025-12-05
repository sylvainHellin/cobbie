# python packages
import json

# ifcopenshell
import ifcopenshell

def get_door_dimensions(model_path: str, door_id: str | None = None, door_name: str | None = None) -> str:
    """Gets the overall width and height of doors from an IFC model.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
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
    ifc_model = ifcopenshell.open(model_path)
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
