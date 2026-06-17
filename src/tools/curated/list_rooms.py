# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def get_containing_storey(space, ifc_model):
    """Get the storey containing a space using ifcRelAggregates relationship."""
    for rel in ifc_model.by_type("IfcRelAggregates"):
        # Check if the relating object is a building storey
        if rel.RelatingObject.is_a("IfcBuildingStorey"):
            # Check if our space is in the related elements
            if space in rel.RelatedObjects:
                return rel.RelatingObject
    return None

def list_rooms(model: ifcopenshell.file, storey: str | None = None):
    """Lists all rooms/spaces in an IFC model with their GUID, short name, and long name.

    Args:
        model (ifcopenshell.file): The already-open IFC model to analyze.
        storey (str, optional): Name of the storey to filter rooms by. If None, returns
            rooms from all storeys.

    Returns:
        list: A list of dictionaries containing room information with keys:
            - guid: The global unique identifier of the space
            - name: The short name (Name property) of the space
            - long_name: The long name from various possible sources in the IFC file
            - storey: The name of the building storey containing this space
    """
    ifc_model = model
    
    # Get all spaces/rooms in the model
    spaces = [space for space in ifc_model.by_type("IfcSpace")]
    
    rooms_info = []
    for space in spaces:
        # Get the containing storey using aggregation relationship
        containing_storey = get_containing_storey(space, ifc_model)
        storey_name = containing_storey.Name if containing_storey else "Unknown Storey"
        
        # Filter by storey if specified
        if storey and storey_name != storey:
            continue
            
        # Get all properties of the space
        psets = ifcopenshell.util.element.get_psets(space)
        
        # Try different approaches to get the long name
        long_name = None
        
        # 1. Try Pset_SpaceCommon.LongName
        if "Pset_SpaceCommon" in psets:
            long_name = psets["Pset_SpaceCommon"].get("LongName")
            
        # 2. Try BaseQuantities.NetFloorArea (some software store room info here)
        if not long_name and "BaseQuantities" in psets:
            long_name = psets["BaseQuantities"].get("NetFloorArea")
            
        # 3. Try space.LongName attribute directly
        if not long_name and hasattr(space, "LongName"):
            long_name = space.LongName
            
        # 4. Try Description as some software use it for long names
        if not long_name and space.Description:
            long_name = space.Description
            
        # 5. Try ObjectType as it sometimes contains additional naming info
        if not long_name and space.ObjectType:
            long_name = space.ObjectType
        
        room_data = {
            "guid": space.GlobalId,
            "name": space.Name if space.Name else "",
            "long_name": str(long_name) if long_name else "",
            "storey": storey_name
        }
        rooms_info.append(room_data)

    return rooms_info 