import ifcopenshell
import ifcopenshell.util.element

from src.config import TEST_IFC_PATH


def get_room_ceiling_height(path_ifc_model: str, room_identifier: str) -> dict:
    """
    Get the ceiling height of a room/space in an IFC model.

    Args:
        path_ifc_model (str): Path to the IFC file
        room_identifier (str or int): Room number, name, or ID

    Returns:
        dict: Dictionary containing:
            - height (float): Ceiling hweight value
            - unit (str): Unit of measurement
            - room_info (dict): Additional room information
            - success (bool): Whether the operation was successful
            - message (str): Informative message about the result
    """
    result = {
        "height": None,
        "unit": None,
        "room_info": {},
        "success": False,
        "message": "",
    }

    try:
        # Load the IFC file
        ifc_file = ifcopenshell.open(path_ifc_model)

        # Get units from the file
        units = ifc_file.by_type("IfcUnitAssignment")  # type:ignore
        length_unit = "meter"  # Default unit
        if units:
            for unit in units[0].Units:
                if unit.is_a("IfcSIUnit") and unit.UnitType == "LENGTHUNIT":
                    length_unit = unit.Name.lower()
                    if hasattr(unit, "Prefix") and unit.Prefix:
                        prefix_map = {
                            "MILLI": "milli",
                            "CENTI": "centi",
                            "DECI": "deci",
                            "KILO": "kilo",
                            "MEGA": "mega",
                        }
                        if unit.Prefix in prefix_map:
                            length_unit = f"{prefix_map[unit.Prefix]}{length_unit}"

        result["unit"] = length_unit

        # Find all spaces/rooms in the model
        spaces = ifc_file.by_type("IfcSpace")  # type:ignore

        # Find the requested room
        target_room = None

        # Check if room_identifier is an integer (could be an ID)
        if isinstance(room_identifier, int) or (
            isinstance(room_identifier, str) and room_identifier.isdigit()
        ):
            room_id = int(room_identifier)
            try:
                target_room = ifc_file.by_id(room_id)
                if not target_room.is_a("IfcSpace"):
                    target_room = None  # Reset if the ID doesn't refer to a space/room
            except:
                pass  # ID not found, continue with other search methods

        # If not found by ID, search by name or number
        if target_room is None:
            for space in spaces:
                # Check various properties that might contain the identifier
                space_name = space.Name if hasattr(space, "Name") else ""
                space_long_name = space.LongName if hasattr(space, "LongName") else ""

                # Also check property sets for room number
                space_number = None
                psets = ifcopenshell.util.element.get_psets(space)
                for pset_name, properties in psets.items():
                    if "Number" in properties:
                        space_number = properties["Number"]

                # Compare with the identifier
                if (
                    (space_name and str(room_identifier) == space_name)
                    or (space_long_name and str(room_identifier) in space_long_name)
                    or (space_number and str(room_identifier) == space_number)
                ):
                    target_room = space
                    break

        if target_room is None:
            result["message"] = f"Room '{room_identifier}' not found in the IFC model"
            return result

        # Room found, get its info
        result["room_info"] = {
            "id": target_room.id(),
            "name": target_room.Name if hasattr(target_room, "Name") else None,
            "long_name": target_room.LongName
            if hasattr(target_room, "LongName")
            else None,
        }

        # Get property sets for the room
        psets = ifcopenshell.util.element.get_psets(target_room)

        # Look for ceiling height in property sets
        height_value = None
        height_sources = []

        # Check in various property sets for height information
        # Revit dimensions usually contain this
        if "PSet_Revit_Dimensions" in psets:
            dims = psets["PSet_Revit_Dimensions"]
            if "Unbounded Height" in dims:
                height_value = dims["Unbounded Height"]
                height_sources.append("Unbounded Height from PSet_Revit_Dimensions")

        # Check in constraints (limit offset is often the height)
        if "PSet_Revit_Constraints" in psets and height_value is None:
            constraints = psets["PSet_Revit_Constraints"]
            if "Limit Offset" in constraints:
                height_value = constraints["Limit Offset"]
                height_sources.append("Limit Offset from PSet_Revit_Constraints")

        # If not found in those specific places, check all property sets
        if height_value is None:
            for pset_name, properties in psets.items():
                for prop_name, prop_value in properties.items():
                    if "height" in prop_name.lower() and isinstance(
                        prop_value, (int, float)
                    ):
                        height_value = prop_value
                        height_sources.append(f"{prop_name} from {pset_name}")
                        break

        # If no height found in properties, try calculating from geometry
        if height_value is None and hasattr(target_room, "Representation"):
            # This would require additional geometry processing using ifcopenshell.geom
            # For simplicity, we're not implementing full geometric analysis here
            height_sources.append("Geometric calculation would be needed")

        # Update the result
        if height_value is not None:
            result["height"] = height_value
            result["success"] = True
            result["message"] = (
                f"Room found and height determined from: {', '.join(height_sources)}"
            )
        else:
            result["message"] = (
                "Room found but couldn't determine ceiling height from available properties"
            )

        return result

    except Exception as e:
        result["message"] = f"Error: {str(e)}"
        return result


if __name__ == "__main__":
    room_name = "A203"
    result = get_room_ceiling_height(
        path_ifc_model=TEST_IFC_PATH, room_identifier=room_name
    )
    print(result)
