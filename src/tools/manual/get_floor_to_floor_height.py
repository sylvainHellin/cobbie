# python packages
import json

# ifcopenshell
import ifcopenshell

def get_floor_to_floor_height(model_path: str) -> str:
    """Gets the floor-to-floor heights between all adjacent building storeys.

    Calculates the vertical distances between consecutive storeys by comparing their
    elevation values. Storeys are sorted by elevation before calculating heights.
    The elevation of a storey is typically measured at its finished floor level.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
            
    Returns:
        str: A JSON string containing floor-to-floor heights in meters (rounded to 2 decimal places).
             Format: {
                "heights": [
                    {
                        "lower_storey": "Level 1",
                        "upper_storey": "Level 2",
                        "height": 3.5
                    },
                    ...
                ]
             }
    """
    ifc_model = ifcopenshell.open(model_path)
    
    # Get all building storeys and sort by elevation
    storeys = ifc_model.by_type("IfcBuildingStorey")
    sorted_storeys = sorted(
        storeys,
        key=lambda x: float(x.Elevation) if hasattr(x, "Elevation") else 0.0
    )
    
    results = {"heights": []}
    
    # Calculate heights between adjacent storeys
    for i in range(len(sorted_storeys) - 1):
        lower = sorted_storeys[i]
        upper = sorted_storeys[i + 1]
        
        try:
            lower_elevation = float(lower.Elevation) if hasattr(lower, "Elevation") else 0.0
            upper_elevation = float(upper.Elevation) if hasattr(upper, "Elevation") else 0.0
            height = upper_elevation - lower_elevation
            
            if height > 0:
                results["heights"].append({
                    "lower_storey": lower.Name,
                    "upper_storey": upper.Name,
                    "height": round(height, 2)
                })
                
        except Exception as e:
            print(f"Error calculating height between {lower.Name} and {upper.Name}: {str(e)}")
            continue

    return json.dumps(results, indent=2) 