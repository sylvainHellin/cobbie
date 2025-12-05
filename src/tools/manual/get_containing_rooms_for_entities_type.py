# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import json


def get_containing_rooms_for_entities_type(
    model_path: str,
    entities: list[str],
) -> str:
    """Gets the rooms/spaces where the specified entity types are located.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        entities (list[str]): List of IFC entity type names
            (e.g., ["IfcFlowTerminal", "IfcFlowController"])

    Returns:
        str: JSON string containing:
            {
                "status": "success" or "error",
                "entities": [
                    {
                        "name": Entity name,
                        "id": Entity GUID,
                        "type": Entity IFC type,
                        "containing_spaces": [
                            {
                                "name": Space name,
                                "id": Space GUID
                            },
                            ...
                        ]
                    },
                    ...
                ],
                "total_count": Total number of entities found,
                "message": Error message if status is "error"
            }
    """
    if not entities:
        return json.dumps(
            {"status": "error", "message": "No entity types provided"}, indent=2
        )

    ifc_model = ifcopenshell.open(model_path)

    try:
        # Initialize result structure
        result = {"status": "success", "entities": [], "total_count": 0}

        spaces = ifc_model.by_type("IfcSpace")

        for entity_type in entities:
            entity_instances = ifc_model.by_type(entity_type)

            for entity in entity_instances:
                entity_info = {
                    "name": getattr(entity, "Name", "Unnamed"),
                    "id": entity.GlobalId,
                    "type": entity_type,
                    "containing_spaces": [],
                }

                for space in spaces:
                    is_contained = False

                    # Check direct spatial containment
                    container = ifcopenshell.util.element.get_container(entity)
                    if container and container == space:
                        is_contained = True

                    # Check space boundaries
                    if not is_contained:
                        space_boundaries = ifc_model.get_inverse(space)
                        for rel in space_boundaries:
                            if rel.is_a("IfcRelSpaceBoundary"):
                                if rel.RelatedBuildingElement == entity:
                                    is_contained = True
                                    break

                    if is_contained:
                        entity_info["containing_spaces"].append(
                            {
                                "name": space.Name if space.Name else "Unnamed Space",
                                "id": space.GlobalId,
                            }
                        )

                result["entities"].append(entity_info)
                count: int = result["total_count"]  # type: ignore
                count = count + 1
                result["total_count"] = count

        if not result["entities"]:
            return json.dumps(
                {
                    "status": "error",
                    "message": "No entities found of the specified types",
                },
                indent=2,
            )

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"Error finding containing rooms: {str(e)}"},
            indent=2,
        )
