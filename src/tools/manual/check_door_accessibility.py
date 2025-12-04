# python packages
import sys
import os
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def check_door_accessibility(model: str = None) -> str:
    """Checks if internal doors meet basic accessibility requirements.
    
    Analyzes door dimensions against common accessibility standards:
    - Minimum clear width of 32 inches (0.813 meters)
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
    
    Returns:
        str: A summary string containing:
            - Whether all doors meet requirements
            - List of non-compliant doors with their issues
    """
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    # Get all doors
    doors = ifc_model.by_type("IfcDoor")
    
    results = {
        'compliant': True,
        'details': []
    }
    
    min_width = 0.813  # 32 inches in meters
    
    for door in doors:
        # Get door properties
        psets = ifcopenshell.util.element.get_psets(door)
        is_external = psets.get("Pset_DoorCommon", {}).get("IsExternal", False)
        
        # Skip external doors
        if is_external:
            continue
            
        # Get dimensions
        width = float(door.OverallWidth) if hasattr(door, 'OverallWidth') else 0
        
        door_info = {
            'name': door.Name if hasattr(door, 'Name') else str(door.id()),
            'width': f"{width:.3f}",
            'compliant': width >= min_width,
            'issue': None
        }
        
        if width < min_width:
            door_info['issue'] = f"Width {width:.3f}m is less than minimum {min_width}m"
            results['compliant'] = False
            
        results['details'].append(door_info)
    
    # Create summary
    if results['compliant']:
        summary = "All internal doors meet basic accessibility requirements"
    else:
        summary = "Some doors do not meet accessibility requirements:\n"
        for door in results['details']:
            if not door['compliant']:
                summary += f"- {door['name']}: {door['issue']}\n"
    
    return summary.strip()

if __name__ == "__main__":
    # Test the function with the architectural model
    print("\nChecking door accessibility in architectural model:")
    print(check_door_accessibility(model="arc"))
    
    # Test with MEP model (might not have doors)
    print("\nChecking door accessibility in MEP model:")
    print(check_door_accessibility(model="mep")) 