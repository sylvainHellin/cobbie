# python packages
import json

# ifcopenshell
import ifcopenshell

def get_type_definitions_and_instances(model: ifcopenshell.file, type_definition_class: str | None = None) -> str:
    """Gets all type definitions and their instances for a specific IFC type.

    This method helps analyze type-instance relationships in an IFC model by:
    1. Finding all type definitions of a specified IFC type class
    2. For each type, collecting all instances/occurrences in the model
    3. Returning structured data about both types and their instances

    Args:
        model (ifcopenshell.file): The already-open IFC model to analyze.
        type_definition_class (str, optional): The IFC type definition class to search for. 
            Must be a valid IFC type class name ending in 'Type'.
            Common examples:
            - 'IfcDoorType' for door types
            - 'IfcWindowType' for window types
            - 'IfcWallType' for wall types
            - 'IfcLightFixtureType' for light fixture types
            - 'IfcFurnitureType' for furniture types
    
    Returns:
        str: JSON string containing:
            {
                "type_count": Total number of type definitions,
                "types": [
                    {
                        "name": Type name,
                        "guid": Type's Global ID,
                        "predefined_type": IFC predefined type if available,
                        "instances": [
                            {
                                "name": Instance name,
                                "guid": Instance Global ID,
                                "type": IFC class of instance
                            },
                            ...
                        ],
                        "instance_count": Number of instances of this type
                    },
                    ...
                ]
            }
    """
    if not type_definition_class:
        return json.dumps({
            "error": "No type definition class provided"
        }, indent=2)
    
    ifc_model = model
    
    try:
        # Get all types of the specified class
        types = ifc_model.by_type(type_definition_class)
        
        if not types:
            return json.dumps({
                "error": f"No {type_definition_class} found in model"
            }, indent=2)
            
        result = {
            "type_count": len(types),
            "types": []
        }
        
        # For each type, get its information and related instances
        for type_def in types:
            instances: list[dict[str, str]] = []

            # Get all elements of this type using inverse relationships
            rel_objects = ifc_model.get_inverse(type_def)
            for rel in rel_objects:
                if rel.is_a("IfcRelDefinesByType"):
                    for instance in rel.RelatedObjects:
                        instance_info = {
                            "name": instance.Name if hasattr(instance, "Name") else "Unnamed",
                            "guid": instance.GlobalId,
                            "type": instance.is_a()
                        }
                        instances.append(instance_info)

            type_info = {
                "name": type_def.Name if hasattr(type_def, "Name") else "Unnamed",
                "guid": type_def.GlobalId,
                "predefined_type": getattr(type_def, "PredefinedType", None),
                "instances": instances,
                "instance_count": len(instances)
            }

            result["types"].append(type_info)
            
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error getting type instances: {str(e)}"
        }, indent=2) 