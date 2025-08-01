
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any

def find_emergency_exits(ifc_file_path: str) -> List[Dict[str, Any]]:
    """
    Identifies emergency exits in an IFC model based on common IFC conventions.
    
    This function looks for emergency exits by checking:
    1. Doors with specific property values (e.g., 'IsEmergencyExit' = True)
    2. Doors in specific property sets (e.g., 'Pset_DoorCommon' with 'Function' = 'emergency')
    3. Doors with specific naming conventions
    
    Note: This implementation is based on common IFC conventions. Different BIM authoring 
    software may use different property sets or conventions.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        
    Returns:
        List[Dict[str, Any]]: List of emergency exits, each represented as a dictionary with:
            - guid: GlobalId of the door
            - name: Name of the door
            - type: IfcType of the element
            - criteria_matched: List of criteria that identified this as an emergency exit
            - properties: Relevant properties of the door
    """
    # Load the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Get all door entities
    doors = model.by_type("IfcDoor")
    
    emergency_exits = []
    
    # Define keywords for naming convention check
    emergency_name_keywords = ['emergency', 'exit', 'egress', 'fire escape']
    
    for door in doors:
        criteria_matched = []
        relevant_properties = {}
        
        # Get all properties of the door
        properties = ifcopenshell.util.element.get_psets(door)
        
        # Check for IsEmergencyExit property (exact requirement)
        # Also check for common variations like IsFireExit
        emergency_property_names = ['IsEmergencyExit', 'IsFireExit', 'FireExit']
        emergency_property_sets = ['Pset_DoorCommon', 'PSet_Revit_Type_Other', 'PSet_Revit_Other', 'Pset_Revit_Door']
        
        for pset_name, pset_data in properties.items():
            if pset_name in emergency_property_sets:
                for prop_name in emergency_property_names:
                    if prop_name in pset_data:
                        prop_value = pset_data[prop_name]
                        # Check for True values (boolean)
                        if prop_value is True:
                            criteria_matched.append(f"{pset_name}.{prop_name} = True")
                            relevant_properties[f"{pset_name}.{prop_name}"] = prop_value
                        # Check for string values that indicate True
                        elif isinstance(prop_value, str) and prop_value.lower() in ['true', 'yes', '1', 't', 'y']:
                            criteria_matched.append(f"{pset_name}.{prop_name} = {prop_value}")
                            relevant_properties[f"{pset_name}.{prop_name}"] = prop_value
                        # Special case for when the property name itself is the value (like 'IsFireExit' = 'IsFireExit')
                        elif isinstance(prop_value, str) and prop_value.lower() == prop_name.lower():
                            criteria_matched.append(f"{pset_name}.{prop_name} = {prop_value} (interpreted as True)")
                            relevant_properties[f"{pset_name}.{prop_name}"] = prop_value
        
        # Check for Pset_DoorCommon with Function = 'emergency' (exact requirement)
        if 'Pset_DoorCommon' in properties:
            pset = properties['Pset_DoorCommon']
            if 'Function' in pset:
                function_value = pset['Function']
                # Check if function value indicates emergency (case insensitive)
                if isinstance(function_value, str) and function_value.lower().strip() == 'emergency':
                    criteria_matched.append("Pset_DoorCommon.Function = emergency")
                    relevant_properties['Pset_DoorCommon.Function'] = function_value
                # Also check for partial matches
                elif isinstance(function_value, str) and 'emergency' in function_value.lower():
                    criteria_matched.append(f"Pset_DoorCommon.Function contains 'emergency' ({function_value})")
                    relevant_properties['Pset_DoorCommon.Function'] = function_value
        
        # Check for naming conventions
        door_name = getattr(door, 'Name', '') or ''
        if door_name:
            name_lower = door_name.lower()
            for keyword in emergency_name_keywords:
                if keyword in name_lower:
                    criteria_matched.append(f"Name contains '{keyword}'")
                    relevant_properties['Name'] = door_name
                    break
        
        # If any criteria matched, add to emergency exits list
        if criteria_matched:
            emergency_exit = {
                "guid": door.GlobalId,
                "name": door_name or "Unnamed",
                "type": door.is_a(),
                "criteria_matched": criteria_matched,
                "properties": relevant_properties
            }
            emergency_exits.append(emergency_exit)
    
    return emergency_exits
