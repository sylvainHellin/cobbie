import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.geom
from typing import List, Dict, Tuple, Set, Any
import numpy as np
from src.tools.initial import classify_spaces


def check_404_2_5_two_doors_in_series(path_ifc_model: str) -> List[str]:
    """
    Check rule 404.2.5: Two Doors in Series
    
    Distance between two hinged or pivoted doors in series shall be 48 inches 
    (1220 mm) minimum plus the width of any door swinging into the space.
    
    One space must be Circulation, the other can be any classification.
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of all door elements that violate this rule
        
    Example:
        >>> guids = check_404_2_5_two_doors_in_series('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} violating doors")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all doors and spaces
    doors = model.by_type('IfcDoor')
    spaces = model.by_type('IfcSpace')
    
    if not doors:
        return []
    
    # Create space info dictionary for classification
    space_info_list = []
    for space in spaces:
        space_info_list.append({
            'guid': space.GlobalId,
            'name': getattr(space, 'LongName', None) or getattr(space, 'Name', '')
        })
    
    # Classify spaces using the classify_spaces tool
    try:
        classified_spaces = classify_spaces(space_info_list, path_ifc_model)
        space_map = {s['guid']: s for s in classified_spaces}
    except Exception as e:
        print(f"Warning: Could not classify spaces: {e}")
        space_map = {}
    
    # Map doors to spaces using IfcRelSpaceBoundary
    door_to_spaces: Dict[str, Set[str]] = {}
    door_data: Dict[str, Dict[str, Any]] = {}
    
    # Get geometry settings
    settings = ifcopenshell.geom.settings()
    
    # First, collect door data and positions
    skipped_doors = 0
    for door in doors:
        try:
            # Get global placement
            placement = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
            global_pos = placement[:3, 3]
            
            # Get geometry
            shape = ifcopenshell.geom.create_shape(settings, door)
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            center = verts.mean(axis=0)
            
            door_data[door.GlobalId] = {
                'guid': door.GlobalId,
                'name': door.Name,
                'width': getattr(door, 'OverallWidth', 0.915),  # Default width if not available
                'global_pos': global_pos,
                'geometry_center': center,
                'door_obj': door
            }
        except Exception as e:
            skipped_doors += 1
            continue
    
    if skipped_doors > 0:
        print(f"Warning: Skipped {skipped_doors} doors due to geometry errors")
    
    # Map doors to spaces using IfcRelSpaceBoundary
    space_boundaries = model.by_type('IfcRelSpaceBoundary')
    for rel in space_boundaries:
        try:
            if hasattr(rel, 'RelatedBuildingElement') and rel.RelatedBuildingElement:
                building_elem = rel.RelatingBuildingElement
                if building_elem and building_elem.is_a('IfcDoor'):
                    door_guid = building_elem.GlobalId
                    
                    if hasattr(rel, 'RelatingSpace') and rel.RelatingSpace:
                        space_guid = rel.RelatingSpace.GlobalId
                        
                        if door_guid not in door_to_spaces:
                            door_to_spaces[door_guid] = set()
                        door_to_spaces[door_guid].add(space_guid)
        except AttributeError:
            continue
    
    # For doors with no space boundaries, try alternative methods
    for door_guid, data in door_data.items():
        if door_guid not in door_to_spaces:
            door_to_spaces[door_guid] = set()
    
    # Find pairs of doors that share at least one space (doors in series)
    violating_guids: List[str] = []
    door_guids = list(door_data.keys())
    
    def get_min_distance_between_doors(door1: Dict[str, Any], door2: Dict[str, Any]) -> float:
        """Calculate minimum distance between two door boundaries."""
        pos1 = door1['global_pos']
        pos2 = door2['global_pos']
        width1 = door1['width']
        width2 = door2['width']
        
        # Simple distance between positions minus half widths
        # This is an approximation - ideally we'd use actual geometry
        center_dist = np.linalg.norm(pos2 - pos1)
        
        # Subtract half widths to get distance between edges
        min_dist = max(0, center_dist - (width1 + width2) / 2)
        
        return min_dist
    
    # Check all pairs of doors
    for i in range(len(door_guids)):
        for j in range(i + 1, len(door_guids)):
            guid1 = door_guids[i]
            guid2 = door_guids[j]
            
            # Check if doors share at least one space (in series)
            spaces1 = door_to_spaces.get(guid1, set())
            spaces2 = door_to_spaces.get(guid2, set())
            shared_spaces = spaces1 & spaces2
            
            if not shared_spaces:
                continue
            
            # Check circulation requirement (one space must be Circulation)
            has_circulation = False
            for space_guid in shared_spaces:
                space = space_map.get(space_guid)
                if space and space.get('classification') == 'Circulation':
                    has_circulation = True
                    break
            
            if not has_circulation:
                continue
            
            # Calculate minimum distance
            door1 = door_data[guid1]
            door2 = door_data[guid2]
            min_dist = get_min_distance_between_doors(door1, door2)
            
            # Required distance: 1.22m + width of door swinging into space
            # Simplified: add one door width (assuming at least one swings into circulation space)
            required_dist = 1.22 + min(door1['width'], door2['width'])
            
            # Check if violation
            if min_dist < required_dist:
                if guid1 not in violating_guids:
                    violating_guids.append(guid1)
                if guid2 not in violating_guids:
                    violating_guids.append(guid2)
    
    return violating_guids