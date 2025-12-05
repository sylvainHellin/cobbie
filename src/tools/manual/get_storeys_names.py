# python packages
import json

# ifcopenshell
import ifcopenshell

def get_storeys_names(model_path: str) -> str:
    """Gets a list of all building storey names in the model.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
    
    Returns:
        str: JSON string containing:
            {
                "storeys": [
                    {
                        "name": "Level 1",
                        "guid": "2O2Fr$t4X7Zf8NOew3FNhv",
                        "elevation": 0.0
                    },
                    ...
                ]
            }
            Storeys are sorted by elevation.
    """
    ifc_model = ifcopenshell.open(model_path)
    
    try:
        # Get all building storeys
        storeys = ifc_model.by_type("IfcBuildingStorey")
        
        # Extract storey information
        storey_info = []
        for storey in storeys:
            info = {
                "name": storey.Name if storey.Name else "Unnamed",
                "guid": storey.GlobalId,
                "elevation": float(storey.Elevation) if hasattr(storey, "Elevation") else 0.0
            }
            storey_info.append(info)
        
        # Sort by elevation
        storey_info.sort(key=lambda x: x["elevation"])
        
        # Print the names in a clean format for console output
        print("Building Storeys (sorted by elevation):")
        for info in storey_info:
            print(f"- {info['name']} (elevation: {info['elevation']}m)")
        
        # Return JSON string
        return json.dumps({"storeys": storey_info}, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Error getting storey names: {str(e)}"}, indent=2) 