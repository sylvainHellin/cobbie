
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Union

def get_door_dimensions_by_function(
    ifc_file_path: str,
    door_function: str,
    dimension_names: List[str]
) -> List[Dict[str, Any]]:
    """
    Identifies doors by their functional role and extracts their dimensional properties.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        door_function (str): Door function type ('main entrance', 'emergency exit', 'interior', 'exterior')
        dimension_names (List[str]): List of dimension names to extract ('Width', 'Height', 'Thickness')
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing door information and requested dimensions
        
    Note:
        This function is designed for IFC models exported from Revit with PSet_Revit property sets.
        Door function identification is based on name patterns and property analysis.
    """
    
    # Load the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Get all door entities
    doors = model.by_type("IfcDoor")
    
    # Initialize result list
    result = []
    
    # Process each door
    for door in doors:
        # Get door properties
        properties = ifcopenshell.util.element.get_psets(door)
        
        # Check if door matches the specified function
        is_match = False
        
        # Check if door is external
        is_external = False
        for prop_set_name, prop_set in properties.items():
            if "doorcommon" in prop_set_name.lower():
                for prop_name, prop_value in prop_set.items():
                    if "external" in prop_name.lower() and prop_value:
                        is_external = True
                        break
            if is_external:
                break
        
        # Also check door name for "exterior"
        door_name = door.Name or ""
        if "exterior" in door_name.lower():
            is_external = True
            
        # Check for "IsFireExit" property for emergency exits
        is_fire_exit = False
        for prop_set_name, prop_set in properties.items():
            if "other" in prop_set_name.lower():
                for prop_name, prop_value in prop_set.items():
                    if "fireexit" in prop_name.lower() and prop_value and prop_value != "IsFireExit":
                        # Check if the value indicates it's actually a fire exit
                        if str(prop_value).lower() in ["true", "yes", "1"]:
                            is_fire_exit = True
                            break
            if is_fire_exit:
                break
        
        # Get door dimensions
        dimensions = {}
        for prop_set_name, prop_set in properties.items():
            if "dimension" in prop_set_name.lower():
                for prop_name, prop_value in prop_set.items():
                    if prop_name in dimension_names:
                        dimensions[prop_name] = prop_value
        
        # Determine if door matches the requested function
        if door_function == "emergency exit" and is_fire_exit:
            is_match = True
        elif door_function == "exterior" and is_external:
            is_match = True
        elif door_function == "interior" and not is_external:
            is_match = True
        elif door_function == "main entrance":
            # Main entrance is typically an external door with width > 1.5m
            width = dimensions.get("Width", 0)
            if is_external and width > 1.5:
                is_match = True
        
        # If door matches function, add to result
        if is_match and dimensions:
            door_info = {
                "GlobalId": door.GlobalId,
                "Name": door.Name,
                "Function": door_function
            }
            
            # Add requested dimensions
            for dim_name in dimension_names:
                door_info[dim_name] = dimensions.get(dim_name, None)
                
            result.append(door_info)
    
    return result
