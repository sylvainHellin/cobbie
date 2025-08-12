
import ifcopenshell
import ifcopenshell.util.element

def get_ceiling_height(model_path: str, room_name: str) -> float:
    """
    Retrieves the ceiling height for a given room in an IFC model.

    Args:
        model_path (str): Path to the IFC model file.
        room_name (str): Name of the room to retrieve the ceiling height for.

    Returns:
        float: The ceiling height of the room.

    Assumptions:
        - The ceiling height is stored in the room's properties or associated elements.
        - The room name is unique within the IFC model.
        - The ceiling height is stored in a property named "CeilingHeight", "Height", "Limit Offset", or similar.
    """
    model = ifcopenshell.open(model_path)
    rooms = model.by_type("IfcSpace")

    for room in rooms:
        if room.Name == room_name:
            properties = ifcopenshell.util.element.get_psets(room)
            for pset_name, pset in properties.items():
                for prop_name, prop_value in pset.items():
                    if "CeilingHeight" in prop_name or "Height" in prop_name or "Limit Offset" in prop_name:
                        return float(prop_value)

            # If not found in properties, check associated elements
            for rel in room.IsDefinedBy:
                if rel.is_a("IfcRelDefinesByProperties"):
                    pset = rel.RelatingPropertyDefinition
                    if pset.is_a("IfcPropertySet"):
                        for prop in pset.HasProperties:
                            if "CeilingHeight" in prop.Name or "Height" in prop.Name or "Limit Offset" in prop.Name:
                                return float(prop.NominalValue.wrappedValue)

    raise ValueError(f"Ceiling height not found for room {room_name}")
