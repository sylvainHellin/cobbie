# python packages
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def get_containing_rooms_for_entity_guids(model: str = None, guids: list[str] = None) -> str:
    """Gets the rooms/spaces where the entities with specified GUIDs are located.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        guids (list[str]): List of entity Global IDs to check
            Example: ["2O2Fr$t4X7Zf8NOew3FNhv", "3hKe29vjL9pPkxwvnQ$KUw"]
            
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
    if not guids:
        return json.dumps({
            "status": "error",
            "message": "No GUIDs provided"
        }, indent=2)
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    try:
        # Initialize result structure
        result = {
            "status": "success",
            "entities": [],
            "total_count": 0
        }
        
        spaces = ifc_model.by_type("IfcSpace")
        
        for guid in guids:
            try:
                entity = ifc_model.by_guid(guid)
                if not entity:
                    continue
                
                entity_info = {
                    "name": getattr(entity, "Name", "Unnamed"),
                    "id": entity.GlobalId,
                    "type": entity.is_a(),
                    "containing_spaces": []
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
                        entity_info["containing_spaces"].append({
                            "name": space.Name if space.Name else "Unnamed Space",
                            "id": space.GlobalId
                        })
                
                result["entities"].append(entity_info)
                result["total_count"] += 1
                
            except Exception as e:
                print(f"Warning: Could not process GUID {guid}: {str(e)}")
                continue
        
        if not result["entities"]:
            return json.dumps({
                "status": "error",
                "message": "No valid entities found for the provided GUIDs"
            }, indent=2)
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error finding containing rooms: {str(e)}"
        }, indent=2)

if __name__ == "__main__":
    # Test with some example GUIDs (update these for your model)
    test_guids = [
        "1hOSvn6df7F8_7GcBWlRGQ",  # Example door GUID
        "1hOSvn6df7F8_7GcBWlSDm",  # Example window GUID
        "invalid_guid"  # Test error handling
    ]
    
    print("\nTesting with example GUIDs:")
    print(get_containing_rooms_for_entity_guids(model="arc", guids=test_guids))
    
    # Test with empty list
    print("\nTesting with empty GUID list:")
    print(get_containing_rooms_for_entity_guids(model="arc", guids=[])) 