# python packages
import sys
import os
import json
import numpy as np
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom

def get_elements_in_room(model: str = None, room_guid: str = None, room_name: str = None) -> str:
    """Gets all elements contained within a specified room/space.
    
    Uses geometric analysis to find elements whose bounding boxes intersect with the room's
    bounding box. This includes all IFC elements like furniture, fixtures, MEP elements, etc.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        room_guid (str, optional): The GlobalId of the room/space to check.
            Example: "1s1jVhK8z0pgKYcr9jt781"
        room_name (str, optional): The name of the room/space to check.
            Example: "Living Room 101"
            Case insensitive matching is used.
            
    Note:
        At least one of room_guid or room_name must be provided.
        If both are provided, room_guid takes precedence.
        If room_name is provided, the first matching room will be used.
            
    Returns:
        str: JSON string containing:
            {
                "room_guid": Room's Global ID,
                "room_name": Room name if available,
                "contained_elements": [
                    {
                        "guid": Element's Global ID,
                        "name": Element name if available,
                        "type": IFC class of the element
                    },
                    ...
                ],
                "element_count": Total number of elements found
            }
            Returns error message if room not found or has no geometry
    """
    if not room_guid and not room_name:
        return json.dumps({
            "error": "You need to provide either the room name or the room guid."
        }, indent=2)
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    try:
        # Find room by name if no guid provided
        if room_name and not room_guid:
            spaces = ifc_model.by_type("IfcSpace")
            room = None
            for space in spaces:
                if space.Name and space.Name.upper() == room_name.upper():
                    room = space
                    room_guid = space.GlobalId
                    break
            if not room:
                return json.dumps({
                    "error": f"No room found with name: {room_name}"
                }, indent=2)
        
        # Find room by guid
        room = ifc_model.by_guid(room_guid)
        if not room:
            return json.dumps({
                "error": f"No room found with GUID: {room_guid}"
            }, indent=2)
        
        # Update settings
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        # First check if room has geometry
        try:
            room_shape = ifcopenshell.geom.create_shape(settings, room)
            room_bbox = get_bounding_box(room_shape)
        except RuntimeError:
            return json.dumps({
                "error": f"Room {room_guid} has no geometric representation"
            }, indent=2)
        
        contained_elements = []
        # Get all elements
        for element in ifc_model.by_type("IfcElement"):
            try:
                if element.ObjectPlacement and element.Representation:
                    element_shape = ifcopenshell.geom.create_shape(settings, element)
                    element_bbox = get_bounding_box(element_shape)
                    if bounding_box_intersect(room_bbox, element_bbox):
                        element_info = {
                            "guid": element.GlobalId,
                            "name": element.Name if element.Name else "Unnamed",
                            "type": element.is_a()
                        }
                        contained_elements.append(element_info)
            except RuntimeError:
                # Skip elements without geometry
                continue
        
        result = {
            "room_guid": room_guid,
            "room_name": room.Name if room.Name else "Unnamed",
            "contained_elements": contained_elements,
            "element_count": len(contained_elements)
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error processing geometric containment: {str(e)}"
        }, indent=2)

def get_bounding_box(shape):
    """Helper function to get bounding box from shape."""
    verts = shape.geometry.verts
    verts = np.array(verts).reshape(-1, 3)
    return np.min(verts, axis=0), np.max(verts, axis=0)

def bounding_box_intersect(bbox1, bbox2):
    """Helper function to check if two bounding boxes intersect."""
    min1, max1 = bbox1
    min2, max2 = bbox2
    return np.all(max1 >= min2) and np.all(max2 >= min1)

if __name__ == "__main__":
    # Test with room GUID
    print("\nTesting with room GUID:")
    print(get_elements_in_room(
        model="arc",
        room_guid="0BTBFw6f90Nfh9rP1dlXr2"  # GUID of room A102
    ))
    
    # Test with room name
    print("\nTesting with room name:")
    print(get_elements_in_room(
        model="arc",
        room_name="A102"  # Living room
    ))
    
    # Test with invalid GUID
    print("\nTesting with invalid room GUID:")
    print(get_elements_in_room(
        model="arc",
        room_guid="invalid_guid"
    ))
    
    # Test with no parameters
    print("\nTesting with no parameters:")
    print(get_elements_in_room(model="arc")) 