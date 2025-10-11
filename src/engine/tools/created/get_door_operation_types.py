import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any, List


def get_door_operation_types(model_path: str) -> Dict[str, Any]:
    """
    Extract door operation types and functional classifications from an IFC model.
    
    This function analyzes IFC door properties to determine door configurations
    and operation mechanisms. It extracts information from property sets that
    contain door operation type information, particularly from ArchiCAD-exported
    models that use German property names.
    
    Args:
        model_path (str): Path to the IFC model file
        
    Returns:
        Dict[str, Any]: Dictionary containing:
            - total_doors (int): Total number of doors
            - door_types (Dict[str, int]): Mapping of door operation types to their counts
            - door_details (List[Dict]): Detailed information for each door including operation type
            
    Note:
        This function is designed to work with IFC models exported from ArchiCAD
        and may need adaptation for models from other BIM software. The function
        looks for specific property sets and property names that may vary between
        different software exports.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Find all door entities
    doors = model.by_type('IfcDoor')
    total_doors = len(doors)
    
    door_types = {}
    door_details = []
    
    for door in doors:
        # Get property sets for this door
        psets = ifcopenshell.util.element.get_psets(door)
        
        # Initialize door information
        door_info = {
            'id': door.GlobalId,
            'name': door.Name,
            'operation_type': 'Unknown',
            'configuration': 'Unknown',
            'panel_count': 0,
            'panel_operations': [],
            'panel_positions': [],
            'panel_widths': [],
            'ifc_operation_type': None
        }
        
        # Extract panel information
        panel_count = 0
        panel_operations = []
        panel_positions = []
        panel_widths = []
        
        # Check for panel properties (ArchiCAD specific)
        for pset_name, pset_data in psets.items():
            if 'Panel' in pset_name and 'Sachmerkmale' in pset_name:
                panel_count += 1
                
                if 'PanelOperation' in pset_data:
                    panel_operations.append(pset_data['PanelOperation'])
                
                if 'PanelPosition' in pset_data:
                    panel_positions.append(pset_data['PanelPosition'])
                
                if 'PanelWidth' in pset_data:
                    panel_widths.append(pset_data['PanelWidth'])
            
            # Check for IFC operation type (ArchiCAD specific)
            if 'IFC Betrieb (ifc_optypestr)' in pset_data:
                door_info['ifc_operation_type'] = pset_data['IFC Betrieb (ifc_optypestr)']
        
        door_info['panel_count'] = panel_count
        door_info['panel_operations'] = panel_operations
        door_info['panel_positions'] = panel_positions
        door_info['panel_widths'] = panel_widths
        
        # Determine door configuration and operation type
        if panel_count == 0:
            # No panel information found, try to use IFC operation type
            if door_info['ifc_operation_type']:
                if 'Einflügeltür' in door_info['ifc_operation_type']:
                    door_info['configuration'] = 'Single'
                    door_info['operation_type'] = 'Single Swing'
                elif 'Zweiflügeltür' in door_info['ifc_operation_type']:
                    door_info['configuration'] = 'Double'
                    if 'Schwingflügel' in door_info['ifc_operation_type']:
                        door_info['operation_type'] = 'Double Swing'
                    else:
                        door_info['operation_type'] = 'Double Door'
        elif panel_count == 1:
            # Single panel door
            door_info['configuration'] = 'Single'
            if panel_operations:
                operation = panel_operations[0]
                if operation == 'SWINGING':
                    door_info['operation_type'] = 'Single Swing'
                elif operation == 'SLIDING':
                    door_info['operation_type'] = 'Single Sliding'
                elif operation == 'DOUBLE_ACTING':
                    door_info['operation_type'] = 'Single Double Acting'
                else:
                    door_info['operation_type'] = f'Single {operation.title()}'
        else:
            # Multi-panel door
            door_info['configuration'] = 'Double' if panel_count == 2 else f'Multi ({panel_count} panels)'
            
            # Determine operation based on panel operations
            if panel_operations:
                unique_operations = list(set(panel_operations))
                if len(unique_operations) == 1:
                    operation = unique_operations[0]
                    if operation == 'SWINGING':
                        door_info['operation_type'] = 'Double Swing'
                    elif operation == 'SLIDING':
                        door_info['operation_type'] = 'Double Sliding'
                    elif operation == 'DOUBLE_ACTING':
                        door_info['operation_type'] = 'Double Double Acting'
                    else:
                        door_info['operation_type'] = f'Double {operation.title()}'
                else:
                    door_info['operation_type'] = f'Mixed Operation ({", ".join(unique_operations)})'
        
        # Fallback to IFC operation type if still unknown
        if door_info['operation_type'] == 'Unknown' and door_info['ifc_operation_type']:
            if 'Einflügeltür' in door_info['ifc_operation_type']:
                door_info['operation_type'] = 'Single Swing'
                door_info['configuration'] = 'Single'
            elif 'Zweiflügeltür' in door_info['ifc_operation_type']:
                door_info['operation_type'] = 'Double Swing'
                door_info['configuration'] = 'Double'
        
        # Count door types
        door_types[door_info['operation_type']] = door_types.get(door_info['operation_type'], 0) + 1
        
        door_details.append(door_info)
    
    return {
        'total_doors': total_doors,
        'door_types': door_types,
        'door_details': door_details
    }