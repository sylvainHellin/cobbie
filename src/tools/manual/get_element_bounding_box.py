# python packages
import json

# ifcopenshell
import ifcopenshell
import ifcopenshell.geom

def get_element_bounding_box(model_path: str, element_guid: str | None = None) -> str:
    """Gets the bounding box coordinates of an IFC element.

    Calculates the minimum and maximum coordinates that form a box
    containing the entire element geometry.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        element_guid (str, optional): The Global ID of the IFC element
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
    
    ifc_model = ifcopenshell.open(model_path)
    
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