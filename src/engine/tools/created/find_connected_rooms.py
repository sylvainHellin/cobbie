
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any

def find_connected_rooms(ifc_file_path: str, room_identifier: str) -> List[Dict[str, Any]]:
    """
    Identifies rooms/spaces that are directly connected to a specified room through doors or other openings.
    
    This function works by:
    1. Finding the specified room in the IFC model by matching Name or LongName
    2. Identifying all doors connected to that room through IfcRelSpaceBoundary relationships
    3. For each connected door, finding the other rooms it connects to
    4. Returning information about all connected rooms
    
    Args:
        ifc_file_path (str): Path to the IFC file
        room_identifier (str): Name, number, or identifier of the room to find connections for
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing information about connected rooms.
                             Each dictionary contains:
                             - room_name: Name of the connected room
                             - room_long_name: Long name of the connected room (if available)
                             - connection_type: Type of connection (e.g., "door")
                             - connecting_element_guid: GlobalId of the connecting element
                             - connecting_element_name: Name of the connecting element
                             Returns empty list if no connections found or room not found.
    """
    try:
        # Open the IFC file
        model = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        print(f"Error opening IFC file: {e}")
        return []
    
    # Find the specified room by searching IfcSpace elements
    spaces = model.by_type("IfcSpace")
    target_space = None
    
    for space in spaces:
        # Check if Name or LongName matches the room_identifier
        if (hasattr(space, 'Name') and space.Name == room_identifier) or \
           (hasattr(space, 'LongName') and space.LongName == room_identifier):
            target_space = space
            break
    
    # If room not found, return empty list
    if target_space is None:
        return []
    
    # Find all doors in the model
    doors = model.by_type("IfcDoor")
    
    # Find all space boundaries in the model
    space_boundaries = model.by_type("IfcRelSpaceBoundary")
    
    # Find all doors that connect to the target space
    connected_doors = set()
    
    # Find boundaries related to the target space
    for boundary in space_boundaries:
        if hasattr(boundary, 'RelatingSpace') and boundary.RelatingSpace == target_space and \
           hasattr(boundary, 'RelatedBuildingElement') and \
           boundary.RelatedBuildingElement and \
           boundary.RelatedBuildingElement.is_a("IfcDoor"):
            connected_doors.add(boundary.RelatedBuildingElement)
    
    # For each connected door, find the other spaces it connects to
    connected_rooms = []
    processed_connections = set()  # To avoid duplicate entries
    
    for door in connected_doors:
        # Find all boundaries related to this door
        door_boundaries = []
        for boundary in space_boundaries:
            if hasattr(boundary, 'RelatedBuildingElement') and \
               boundary.RelatedBuildingElement == door:
                door_boundaries.append(boundary)
        
        # For each boundary of this door, find the connected spaces (excluding target space)
        for boundary in door_boundaries:
            if hasattr(boundary, 'RelatingSpace') and boundary.RelatingSpace != target_space:
                connected_space = boundary.RelatingSpace
                if connected_space:
                    # Create a unique key to avoid duplicate connections
                    connection_key = (connected_space.GlobalId, door.GlobalId)
                    if connection_key in processed_connections:
                        continue
                    processed_connections.add(connection_key)
                    
                    # Create the result dictionary
                    room_info = {
                        "room_name": getattr(connected_space, 'Name', ''),
                        "room_long_name": getattr(connected_space, 'LongName', ''),
                        "connection_type": "door",
                        "connecting_element_guid": door.GlobalId,
                        "connecting_element_name": getattr(door, 'Name', '')
                    }
                    
                    connected_rooms.append(room_info)
    
    return connected_rooms
