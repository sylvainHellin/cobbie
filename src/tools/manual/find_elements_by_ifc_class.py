# python packages
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell

def find_elements_by_ifc_class(model: str = None, element_type: str = None) -> str:
    """Retrieves basic information about all elements of a specified IFC type from the model.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        element_type (str): The IFC entity type to search for (e.g., 'IfcWall', 'IfcDoor')
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
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
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

if __name__ == "__main__":
    # Test with common IFC classes
    test_types = [
        "IfcWall",
        "IfcDoor",
        "IfcWindow",
        "IfcSpace",
        "IfcFlowTerminal"  # MEP element
    ]
    
    print("\nTesting with architectural model:")
    for element_type in test_types:
        print(f"\nSearching for {element_type}:")
        print(find_elements_by_ifc_class(model="arc", element_type=element_type))
    
    # Test with invalid type
    print("\nTesting with invalid type:")
    print(find_elements_by_ifc_class(model="arc", element_type="InvalidType"))
    
    # Test with no type
    print("\nTesting with no type:")
    print(find_elements_by_ifc_class(model="arc")) 