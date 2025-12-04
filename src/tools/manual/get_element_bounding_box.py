# python packages
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.geom

def get_element_bounding_box(model: str = None, element_guid: str = None) -> str:
    """Gets the bounding box coordinates of an IFC element.
    
    Calculates the minimum and maximum coordinates that form a box 
    containing the entire element geometry.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        element_guid (str): The Global ID of the IFC element
            Example: "2O2Fr$t4X7Zf8NOew3FNhv"
            
    Returns:
        str: JSON string containing:
            {
                "guid": Element's Global ID,
                "name": Element name if available,
                "type": IFC class of the element,
                "bounding_box": {
                    "min": [x, y, z],  # Minimum coordinates in meters
                    "max": [x, y, z]   # Maximum coordinates in meters
                }
            }
            Returns error message if element not found or has no geometry
    """
    if not element_guid:
        return json.dumps({"error": "No element GUID provided"}, indent=2)
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    try:
        # Get element by GUID
        element = ifc_model.by_guid(element_guid)
        if not element:
            return json.dumps({
                "error": f"No element found with GUID: {element_guid}"
            }, indent=2)
        
        # Create geometry settings
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        try:
            # Create shape from geometry
            shape = ifcopenshell.geom.create_shape(settings, element)
            if not shape:
                return json.dumps({
                    "error": f"Element {element_guid} has no geometry"
                }, indent=2)
            
            # Get vertices from the geometry
            geometry = shape.geometry
            verts = geometry.verts
            
            # Calculate bounding box
            bbox = {
                'min': [float('inf'), float('inf'), float('inf')],
                'max': [float('-inf'), float('-inf'), float('-inf')]
            }
            
            # Vertices are stored as a flat array [x1,y1,z1,x2,y2,z2,...], so iterate in steps of 3
            for i in range(0, len(verts), 3):
                vertex = [verts[i], verts[i+1], verts[i+2]]
                for j in range(3):  # x, y, z
                    bbox['min'][j] = min(bbox['min'][j], vertex[j])
                    bbox['max'][j] = max(bbox['max'][j], vertex[j])
            
            # Round coordinates to 3 decimal places
            bbox['min'] = [round(x, 3) for x in bbox['min']]
            bbox['max'] = [round(x, 3) for x in bbox['max']]
            
            # Create result with element info
            result = {
                "guid": element_guid,
                "name": element.Name if hasattr(element, "Name") else "Unnamed",
                "type": element.is_a(),
                "bounding_box": bbox
            }
            
            return json.dumps(result, indent=2)
            
        except RuntimeError:
            return json.dumps({
                "error": f"Could not process geometry for element {element_guid}"
            }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error calculating bounding box: {str(e)}"
        }, indent=2)

if __name__ == "__main__":
    # Test with some example GUIDs (update these for your model)
    test_guids = [
        "1hOSvn6df7F8_7GcBWlRGQ",  # Example door GUID
        "1hOSvn6df7F8_7GcBWlSDm",  # Example window GUID
        "invalid_guid"  # Test error handling
    ]
    
    print("\nTesting with example GUIDs:")
    for guid in test_guids:
        print(f"\nGetting bounding box for {guid}:")
        print(get_element_bounding_box(model="arc", element_guid=guid))
    
    # Test with no GUID
    print("\nTesting with no GUID:")
    print(get_element_bounding_box(model="arc")) 