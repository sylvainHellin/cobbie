import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
from typing import List, Dict, Set
import numpy as np
import re

def check_404_2_5_two_doors_in_series(path_ifc_model: str) -> List[str]:
    """
    Check if doors in series meet the minimum distance requirement per ADA 404.2.5.
    
    Distance between two hinged or pivoted doors in series shall be 48 inches 
    (1220 mm) minimum plus the width of any door swinging into the space.
    One space must be Circulation, the other can be any classification.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of all doors that violate the rule.
        
    Example:
        >>> guids = check_404_2_5_two_doors_in_series('model.ifc')
        >>> print(f"Found {len(guids)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Constants
    MIN_DISTANCE = 1.22  # 1220 mm in meters
    
    # Get all doors
    doors = model.by_type('IfcDoor')
    if not doors:
        return []
    
    # Get all spaces and classify them
    spaces = model.by_type('IfcSpace')
    space_data = []
    for space in spaces:
        space_info = {
            'guid': space.GlobalId,
            'name': space.Name or '',
            'long_name': getattr(space, 'LongName', '') or ''
        }
        space_data.append(space_info)
    
    # Classify spaces
    try:
        classified_spaces = classify_spaces(space_data, path_ifc_model)
        space_classification = {s['guid']: s['classification'] for s in classified_spaces}
    except Exception:
        # If classification fails, assume unclassified
        space_classification = {s['guid']: 'Unclassified' for s in space_data}
    
    # Build door-to-spaces mapping using IfcRelSpaceBoundary
    door_to_spaces: Dict[str, Set[str]] = {}
    rel_boundaries = model.by_type('IfcRelSpaceBoundary')
    
    for rel in rel_boundaries:
        if hasattr(rel, 'RelatedBuildingElement') and rel.RelatedBuildingElement:
            if rel.RelatedBuildingElement.is_a('IfcDoor'):
                door_guid = rel.RelatedBuildingElement.GlobalId
                space = rel.RelatingSpace
                if space:
                    if door_guid not in door_to_spaces:
                        door_to_spaces[door_guid] = set()
                    door_to_spaces[door_guid].add(space.GlobalId)
    
    # Build door data dictionary with positions
    door_data: Dict[str, Dict] = {}
    skipped_count = 0
    
    for door in doors:
        guid = door.GlobalId
        
        # Get door position
        position = None
        if door.ObjectPlacement:
            try:
                matrix = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
                position = np.array([matrix[0, 3], matrix[1, 3], matrix[2, 3]])
            except Exception:
                skipped_count += 1
                continue
        
        if position is None:
            skipped_count += 1
            continue
        
        # Get door width
        width = 0.915  # Default width in meters
        psets = ifcopenshell.util.element.get_psets(door)
        door_common = psets.get('Pset_DoorCommon', {})
        
        # Try to extract width from Reference or other properties
        ref = door_common.get('Reference', '')
        if ref:
            try:
                # Look for pattern like "0915" before 'x' or space
                match = re.search(r'[:\s](\d{3,4})\s*[xX]', ref)
                if match:
                    width_mm = float(match.group(1))
                    width = width_mm / 1000.0  # Convert to meters
            except Exception:
                pass
        
        # Check operation type (hinged or pivoted) - assume most doors are for accessibility
        operation_type = 'HINGED_OR_PIVOTED'
        door_type = ifcopenshell.util.element.get_type(door)
        if door_type:
            pred_type = getattr(door_type, 'PredefinedType', None)
            if pred_type:
                pred_type_str = str(pred_type).upper()
                if 'HINGE' in pred_type_str or 'PIVOT' in pred_type_str or 'SWING' in pred_type_str:
                    operation_type = 'HINGED_OR_PIVOTED'
        
        door_data[guid] = {
            'door': door,
            'position': position,
            'width': width,
            'operation_type': operation_type,
            'spaces': door_to_spaces.get(guid, set())
        }
    
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} doors due to missing placement data")
    
    # Find doors that are in circulation-adjacent spaces
    circulation_door_guids: Set[str] = set()
    
    for guid, data in door_data.items():
        spaces = data['spaces']
        for space_guid in spaces:
            if space_classification.get(space_guid, 'Unclassified') == 'Circulation':
                circulation_door_guids.add(guid)
                break
    
    # Find pairs of doors that share a circulation space and are too close
    violating_guids: Set[str] = set()
    
    # Check all pairs of doors in circulation areas
    circulation_guids_list = list(circulation_door_guids)
    
    for i in range(len(circulation_guids_list)):
        for j in range(i + 1, len(circulation_guids_list)):
            guid1 = circulation_guids_list[i]
            guid2 = circulation_guids_list[j]
            
            data1 = door_data[guid1]
            data2 = door_data[guid2]
            
            # Check if doors share a common space
            common_spaces = data1['spaces'] & data2['spaces']
            
            # Check if common space includes circulation
            has_circulation_in_common = False
            for space_guid in common_spaces:
                if space_classification.get(space_guid, 'Unclassified') == 'Circulation':
                    has_circulation_in_common = True
                    break
            
            # Only check if they share a circulation space
            if not has_circulation_in_common:
                continue
            
            # Calculate distance between doors
            pos1 = data1['position']
            pos2 = data2['position']
            distance = np.linalg.norm(pos1[:2] - pos2[:2])  # XY distance only
            
            # Calculate required minimum distance
            # Rule: 1.22m + width of door swinging into space
            # Using the larger width of the two doors
            required_distance = MIN_DISTANCE + max(data1['width'], data2['width'])
            
            if distance < required_distance:
                violating_guids.add(guid1)
                violating_guids.add(guid2)
    
    return sorted(list(violating_guids))