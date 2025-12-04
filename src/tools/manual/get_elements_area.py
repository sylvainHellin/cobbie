# python packages
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.shape
import ifcopenshell.geom

def get_elements_area(model: str = None, guids: list[str] = None) -> str:
    """Gets the area of specified elements by their GUIDs.
    
    Calculates the area of each element and provides a total area.
    For each element, calculates projected areas on each axis and uses the largest value.
    Useful for quantity takeoffs and material area calculations.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        guids (list[str]): List of element Global IDs to calculate areas for
            Example: ["2O2Fr$t4X7Zf8NOew3FNhv", "3hKe29vjL9pPkxwvnQ$KUw"]
            
    Returns:
        str: JSON string containing:
            {
                "total_area": Sum of all element areas in square meters,
                "elements": [
                    {
                        "guid": Element's Global ID,
                        "name": Element name if available,
                        "type": IFC class of the element,
                        "area": Area in square meters
                    },
                    ...
                ],
                "errors": Array of any GUIDs that couldn't be processed
            }
    """
    if not guids:
        return json.dumps({"error": "No element GUIDs provided"}, indent=2)
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    try:
        # Initialize results structure
        result = {
            "total_area": 0.0,
            "elements": [],
            "errors": []
        }
        
        # Create geometry settings
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        # Process each GUID
        for guid in guids:
            try:
                # Get element by GUID
                element = ifc_model.by_guid(guid)
                if not element:
                    result["errors"].append({
                        "guid": guid,
                        "error": "Element not found"
                    })
                    continue
                
                # Create shape from geometry
                shape = ifcopenshell.geom.create_shape(settings, element)
                if not shape:
                    result["errors"].append({
                        "guid": guid,
                        "error": "No geometry found"
                    })
                    continue
                
                # Calculate projected area for each axis and keep the highest value
                projected_areas = []
                for axis in ["X", "Y", "Z"]:
                    area = ifcopenshell.util.shape.get_side_area(shape.geometry, axis=axis)
                    projected_areas.append(area)

                # select the largest projection
                area = max(projected_areas)

                # Add element info to results
                element_info = {
                    "guid": guid,
                    "name": element.Name if hasattr(element, "Name") else "Unnamed",
                    "type": element.is_a(),
                    "area": round(area, 3)  # Round to 3 decimal places
                }
                result["elements"].append(element_info)
                result["total_area"] += area
                
            except Exception as e:
                result["errors"].append({
                    "guid": guid,
                    "error": str(e)
                })
        
        # Round total area
        result["total_area"] = round(result["total_area"], 3)
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error calculating areas: {str(e)}"
        }, indent=2)

if __name__ == "__main__":
    # Test with some example GUIDs (update these for your model)
    test_guids = [
        "2O2Fr$t4X7Zf8NOew3FNr2",  # Example wall GUID
        "2OBrcmyk58NupXoVOHUtxr",  # Example floor GUID
        "invalid_guid"  # Test error handling
    ]
    
    print("\nTesting with example GUIDs:")
    print(get_elements_area(model="arc", guids=test_guids))
    
    # Test with empty list
    print("\nTesting with empty GUID list:")
    print(get_elements_area(model="arc", guids=[])) 