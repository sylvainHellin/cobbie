#%%
# python packages
import sys
import os
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom

def get_room_ceiling_height(name: str = None, guid: str = None, model: str = None):
    """Gets the ceiling height of a specific room in an IFC model.
    
    Finds a room/space by either its GUID or by searching its identifiers (name, description, 
    or long name) for a matching string. Once found, calculates the vertical dimension of 
    the space using its geometric representation.

    Args:
        name (str, optional): String to search for in room identifiers. Can be a full or 
            partial match. Case-insensitive.
        guid (str, optional): Global unique identifier of the space. Provides direct lookup.
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.

    Returns:
        str: The ceiling height in meters, rounded to 2 decimal places. Returns None if the
            room is not found or if there are geometry processing errors.

    Raises:
        ValueError: If neither name nor guid is provided.

    Note:
        When searching by name, matches are checked against:
        - The room's Name property
        - The room's Description property
        - The LongName property in Pset_SpaceCommon
    """
    if name is None and guid is None:
        raise ValueError("Either name or guid must be provided")
        
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    # Get all spaces/rooms in the models
    spaces = [space for space in ifc_model.by_type("IfcSpace")]
    
    # Find the space by GUID or name
    target_space = None
    
    if guid:
        # Direct GUID lookup
        target_space = ifc_model.by_guid(guid)
    else:
        # Name-based search with existing logic
        for space in spaces:
            # Get all properties of the space
            psets = ifcopenshell.util.element.get_psets(space)
            
            # Check name
            if name.upper() in space.Name.upper():
                target_space = space
                break
                
            # Check description if it exists
            if space.Description and name.upper() in space.Description.upper():
                target_space = space
                break
                
            # Check LongName property if it exists in Pset_SpaceCommon
            long_name = psets.get("Pset_SpaceCommon", {}).get("LongName", "")
            if long_name and name.upper() in str(long_name).upper():
                target_space = space
                break
    
    if not target_space:
        return None
        
    # Get the geometry
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    try:
        shape = ifcopenshell.geom.create_shape(settings, target_space)
        geometry = shape.geometry
        # Get the height (Z dimension) of the space
        height = ifcopenshell.util.shape.get_z(geometry)
        return str(round(height, 2))
        
    except RuntimeError:
        return None

if __name__ == "__main__":
    # Test the function with a room from the architectural model
    height = get_room_ceiling_height(guid="0BTBFw6f90Nfh9rP1dlXr2", model="arc")
    print(height) 
    height = get_room_ceiling_height(name="R301", model="arc")
    print(height) 
# %%
