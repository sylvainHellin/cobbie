import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any


def get_door_width_by_guid(model_path: str, guid: str) -> Dict[str, Any]:
    """
    Retrieve door width by GlobalId from IFC models with priority-based source selection.
    
    This function searches for width-related properties across multiple sources in priority order:
    1. OverallWidth from direct attributes (highest confidence)
    2. Width from PSet_Revit_Type_Dimensions (medium confidence)
    3. Other width-related properties from various property sets (low confidence)
    
    Args:
        model_path (str): Path to the IFC model file
        guid (str): GlobalId of the door element
        
    Returns:
        Dict[str, Any]: Dictionary containing:
            - width (float): Width value in meters (0.0 if not found)
            - source (str): Source property name ("none" if not found)
            - confidence (str): "high", "medium", "low", or "none"
            - all_sources (dict): All found width sources for verification
            
    Assumptions:
        - The IFC model was exported from Revit and may contain Revit-specific property sets like PSet_Revit_Type_Dimensions
        - Width values are stored in meters (SI units)
        - Multiple property sources may contain width information, requiring priority-based selection
    """
    
    # Initialize result dictionary
    result = {
        'width': 0.0,
        'source': 'none',
        'confidence': 'none',
        'all_sources': {}
    }
    
    try:
        # Open the IFC model
        model = ifcopenshell.open(model_path)
        
        # Find the door by GlobalId
        door = model.by_guid(guid)
        
        # Check if the found element is actually a door
        if not door or door.is_a() != 'IfcDoor':
            return result
            
        # Get all property sets for the door
        psets = ifcopenshell.util.element.get_psets(door)
        
        # Dictionary to store all found width sources
        all_width_sources = {}
        
        # Priority 1: OverallWidth from direct attributes (highest confidence)
        overall_width = getattr(door, 'OverallWidth', None)
        if overall_width is not None:
            all_width_sources['OverallWidth'] = overall_width
            
        # Priority 2: Width from PSet_Revit_Type_Dimensions (medium confidence)
        if 'PSet_Revit_Type_Dimensions' in psets and 'Width' in psets['PSet_Revit_Type_Dimensions']:
            all_width_sources['PSet_Revit_Type_Dimensions.Width'] = psets['PSet_Revit_Type_Dimensions']['Width']
        
        # Priority 3: Other width-related properties (low confidence)
        for pset_name, pset_data in psets.items():
            for prop_name, prop_value in pset_data.items():
                # Skip properties we already processed
                if (pset_name == 'PSet_Revit_Type_Dimensions' and prop_name == 'Width') or prop_name == 'OverallWidth':
                    continue
                    
                # Look for width-related properties (case insensitive)
                if 'width' in prop_name.lower():
                    source_name = f'{pset_name}.{prop_name}'
                    # Only add if it's a numeric value and seems like a main width
                    if isinstance(prop_value, (int, float)) and prop_value > 0:
                        # Prioritize properties that seem to be main door width
                        if any(keyword in prop_name.lower() for keyword in ['width', 'opening', 'unit']):
                            all_width_sources[source_name] = prop_value
        
        # Store all found sources
        result['all_sources'] = all_width_sources
        
        # Select the best width source based on priority
        selected_width = None
        selected_source = None
        selected_confidence = 'none'
        
        # Check OverallWidth first (highest priority)
        if 'OverallWidth' in all_width_sources:
            selected_width = all_width_sources['OverallWidth']
            selected_source = 'OverallWidth'
            selected_confidence = 'high'
        # Then check PSet_Revit_Type_Dimensions.Width
        elif 'PSet_Revit_Type_Dimensions.Width' in all_width_sources:
            selected_width = all_width_sources['PSet_Revit_Type_Dimensions.Width']
            selected_source = 'PSet_Revit_Type_Dimensions.Width'
            selected_confidence = 'medium'
        # Otherwise, use the first available width source (low confidence)
        elif all_width_sources:
            # Get the first available source
            selected_source = list(all_width_sources.keys())[0]
            selected_width = all_width_sources[selected_source]
            selected_confidence = 'low'
        
        # Use width value directly (assumed to be in meters)
        if selected_width is not None:
            result['width'] = float(selected_width)
            result['source'] = selected_source
            result['confidence'] = selected_confidence
        
    except Exception as e:
        # If any error occurs, return the default result with error information
        result['all_sources'] = {'error': str(e)}
    
    return result