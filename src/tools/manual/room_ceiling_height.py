# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom

def get_room_ceiling_height(model_path: str, name: str | None = None, guid: str | None = None):
    """Gets the ceiling height of a specific room in an IFC model.

    Finds a room/space by either its GUID or by searching its identifiers (name, description,
    or long name) for a matching string. Once found, calculates the vertical dimension of
    the space using its geometric representation.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        name (str, optional): String to search for in room identifiers. Can be a full or
            partial match. Case-insensitive.
        guid (str, optional): Global unique identifier of the space. Provides direct lookup.

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

    ifc_model = ifcopenshell.open(model_path)
    
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
        geometry = shape.geometry()
        # Get the height (Z dimension) of the space
        height = ifcopenshell.util.shape.get_z(geometry)
        return str(round(height, 2))


    except RuntimeError:
        return None
