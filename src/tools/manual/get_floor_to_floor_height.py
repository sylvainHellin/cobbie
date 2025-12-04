# python packages
import sys
import os
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell

def get_floor_to_floor_height(model: str = None) -> str:
    """Gets the floor-to-floor heights between all adjacent building storeys.
    
    Calculates the vertical distances between consecutive storeys by comparing their 
    elevation values. Storeys are sorted by elevation before calculating heights.
    The elevation of a storey is typically measured at its finished floor level.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
            
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
    import json
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
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

if __name__ == "__main__":
    # Test the function
    print("\nCalculating all floor-to-floor heights:")
    print(get_floor_to_floor_height(model="arc")) 