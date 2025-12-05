# ifcopenshell
import ifcopenshell
import ifcopenshell.util.shape
import ifcopenshell.geom
import json

def get_elements_volume(model_path: str, guids: list[str] | None = None) -> str:
    """Gets the volume of specified elements by their GUIDs.

    Calculates the volume of each element and provides a total volume.
    Useful for quantity takeoffs, material volume calculations, and mass studies.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        guids (list[str]): List of element Global IDs to calculate volumes for
            Example: ["2O2Fr$t4X7Zf8NOew3FNhv", "3hKe29vjL9pPkxwvnQ$KUw"]
            
    Returns:
        str: JSON string containing:
            {
                "total_volume": Sum of all element volumes in cubic meters,
                "elements": [
                    {
                        "guid": Element's Global ID,
                        "name": Element name if available,
                        "type": IFC class of the element,
                        "volume": Volume in cubic meters
                    },
                    ...
                ],
                "errors": Array of any GUIDs that couldn't be processed
            }
    """
    if not guids:
        return json.dumps({"error": "No element GUIDs provided"}, indent=2)

    ifc_model = ifcopenshell.open(model_path)
    
    try:
        # Initialize results structure
        result = {
            "total_volume": 0.0,
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

                # Calculate volume
                geom = shape.geometry()
                volume = ifcopenshell.util.shape.get_volume(geom)
                
                # Add element info to results
                element_info = {
                    "guid": guid,
                    "name": element.Name if hasattr(element, "Name") else "Unnamed",
                    "type": element.is_a(),
                    "volume": round(volume, 3)  # Round to 3 decimal places
                }
                result["elements"].append(element_info)
                total: float = result["total_volume"]  # type: ignore
                total = total + volume
                result["total_volume"] = total
                
            except Exception as e:
                result["errors"].append({
                    "guid": guid,
                    "error": str(e)
                })
        
        # Round total volume
        total_value: float = result["total_volume"]  # type: ignore
        result["total_volume"] = round(total_value, 3)
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error calculating volumes: {str(e)}"
        }, indent=2) 