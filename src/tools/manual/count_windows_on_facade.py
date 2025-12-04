# python packages
import sys
import os
import math
from typing import Dict, List, Tuple
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation

# local imports
from tools.is_georeferenced import is_georeferenced

def count_windows_on_facade(model: str = None, tolerance_degrees: float = 45, depth: int = 0, use_true_north: bool = True) -> Dict:
    """Count and analyze windows on facades with different levels of detail.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        tolerance_degrees (float): Angle tolerance for considering a window to face the direction
        depth (int): Level of detail for the return value:
            0: Returns total number of windows
            1: Adds breakdown of windows per direction
            2: Adds detailed list of windows with their directions
        use_true_north (bool): Whether to use true north (considering project rotation) or geometric north
    
    Returns:
        Dict: A dictionary with increasing level of detail based on depth
    """
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    windows = ifc_model.by_type("IfcWindow")
    
    # Base result with total count
    result = {"total": len(windows)}
    if depth == 0:
        return result
        
    # Get true north correction
    true_north_correction = 0
    if use_true_north and is_georeferenced(model=model):
        try:
            angle = ifcopenshell.util.geolocation.get_true_north(ifc_model)
            true_north_correction = math.degrees(angle) if angle is not None else 0
        except Exception as e:
            print(f"Warning: Using geometric north due to: {str(e)}")

    # Direction mapping with corrected angles
    directions = {
        (0 + true_north_correction) % 360: "NORTH",
        (90 + true_north_correction) % 360: "EAST",
        (180 + true_north_correction) % 360: "SOUTH",
        (270 + true_north_correction) % 360: "WEST"
    }
    
    direction_counts = {dir_name: 0 for dir_name in ["NORTH", "SOUTH", "EAST", "WEST"]}
    window_details = []
    
    for window in windows:
        # Get window orientation from wall or window placement
        orientation = None
        try:
            wall = ifcopenshell.util.element.get_container(window)
            placement = wall if wall and wall.is_a('IfcWall') else window
            matrix = ifcopenshell.util.placement.get_local_placement(placement.ObjectPlacement)
            angle = (math.degrees(math.atan2(matrix[0][0], matrix[0][1])) + 90) % 360
            
            # Find closest cardinal direction
            closest_angle = min(directions.keys(), 
                              key=lambda x: min(abs(x - angle), 360 - abs(x - angle)))
            direction = directions[closest_angle]
            
            direction_counts[direction] += 1
            if depth == 2:
                window_details.append((window.id(), direction))
                
        except Exception:
            continue
    
    result["by_direction"] = direction_counts
    if depth == 2:
        result["windows"] = sorted(window_details, key=lambda x: x[0])
    
    return result

if __name__ == "__main__":
    # Test all depth levels with both geometric and true north
    for use_true_north in [True, False]:
        print(f"\nUsing {'true' if use_true_north else 'geometric'} north:")
        
        print("\nDepth 0 (total only):")
        print(count_windows_on_facade(model="arc", depth=0, use_true_north=use_true_north))
        
        print("\nDepth 1 (with direction breakdown):")
        print(count_windows_on_facade(model="arc", depth=1, use_true_north=use_true_north))
        
        print("\nDepth 2 (with window details):")
        result = count_windows_on_facade(model="arc", depth=2, use_true_north=use_true_north)
        print(f"Total windows: {result['total']}")
        print("\nBy direction:")
        for direction, count in result["by_direction"].items():
            print(f"{direction}: {count}")
        print("\nDetailed listing:")
        for window_id, direction in result["windows"]:
            print(f"Window {window_id}: {direction}") 