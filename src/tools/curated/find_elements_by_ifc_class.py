# python packages
import json

# ifcopenshell
import ifcopenshell

def find_elements_by_ifc_class(model: ifcopenshell.file, element_type: str | None = None) -> str:
    """Retrieves basic information about all elements of a specified IFC type from the model.

    Args:
        model (ifcopenshell.file): The already-open IFC model to analyze.
        element_type (str, optional): The IFC entity type to search for (e.g., 'IfcWall', 'IfcDoor')
            Must be a valid IFC entity type name.
            
    Returns:
        str: JSON string containing:
            {
                "total_count": Total number of elements found,
                "elements": [
                    {
                        "guid": Element's Global ID,
                        "name": Element name if available,
                        "type": IFC class of the element,
                        "description": Element description if available
                    },
                    ...
                ]
            }
            Returns error message if type not found or other error occurs.
    """
    if not element_type:
        return json.dumps({
            "error": "No element type specified"
        }, indent=2)
    
    ifc_model = model
    
    try:
        # Get all elements of the specified type
        elements = ifc_model.by_type(element_type)
        
        if not elements:
            return json.dumps({
                "error": f"No elements found of type {element_type}"
            }, indent=2)
        
        # Build list of element info
        element_list = []
        for element in elements:
            element_info = {
                "guid": element.GlobalId,
                "name": element.Name if element.Name else "Unnamed",
                "type": element.is_a(),
                "description": element.Description if hasattr(element, "Description") else None
            }
            element_list.append(element_info)
        
        # Sort elements by name for consistent output
        element_list.sort(key=lambda x: x["name"])
        
        result = {
            "total_count": len(element_list),
            "elements": element_list
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error finding elements: {str(e)}"
        }, indent=2) 