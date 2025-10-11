import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *


def analyze_space_layout_and_fire_ratings(
    model_path: str,
    space_patterns: Optional[List[str]] = None,
    target_spaces: Optional[List[str]] = None,
    level_filter: Optional[str] = None,
    include_fire_ratings: bool = True,
    spatial_analysis: bool = True
) -> Dict[str, Any]:
    """
    Comprehensive tool that analyzes space layouts and fire ratings in IFC models.
    
    This function extracts detailed space information, analyzes spatial relationships,
    and checks fire ratings of separating elements. It works with both Revit and ArchiCAD
    exports and handles standard IFC property sets.
    
    Args:
        model_path: Path to IFC file
        space_patterns: List of patterns to identify spaces of interest (e.g., ['BURO*', 'OFFICE*'])
        target_spaces: List of specific space names to analyze
        level_filter: Filter by building level name
        include_fire_ratings: Whether to analyze fire ratings of separating elements
        spatial_analysis: Whether to analyze spatial relationships between spaces
    
    Returns:
        Dictionary containing:
        - spaces_found: List of identified spaces with full properties
        - layout_summary: Room counts by type, total areas, level organization
        - spatial_relationships: Mapping of space adjacencies and connections
        - fire_rating_analysis: Fire ratings of walls between spaces
        - separating_elements: Elements that separate identified spaces
        - layout_description: Natural language description of the space layout
    """
    
    # Load the IFC model
    try:
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise ValueError(f"Failed to load IFC model: {e}")
    
    # Initialize result dictionary
    result = {
        'spaces_found': [],
        'layout_summary': {},
        'spatial_relationships': {},
        'fire_rating_analysis': {},
        'separating_elements': [],
        'layout_description': ''
    }
    
    # Get all spaces from the model
    all_spaces = model.by_type('IfcSpace')
    
    # Filter spaces based on criteria
    filtered_spaces = []
    
    for space in all_spaces:
        space_name = space.Name or ''
        space_longname = space.LongName or ''
        
        # Check if space matches any of the filter criteria
        include_space = False
        
        # Check target spaces
        if target_spaces and space_name in target_spaces:
            include_space = True
        
        # Check space patterns
        if space_patterns and not include_space:
            for pattern in space_patterns:
                if pattern.endswith('*'):
                    if space_name.startswith(pattern[:-1]) or space_longname.startswith(pattern[:-1]):
                        include_space = True
                        break
                elif pattern.lower() in space_name.lower() or pattern.lower() in space_longname.lower():
                    include_space = True
                    break
        
        # If no filters specified, include all spaces
        if not target_spaces and not space_patterns:
            include_space = True
        
        if include_space:
            # Check level filter
            if level_filter:
                container = ifcopenshell.util.element.get_container(space)
                if container and container.Name == level_filter:
                    filtered_spaces.append(space)
            else:
                filtered_spaces.append(space)
    
    # Extract comprehensive space properties
    spaces_data = []
    space_by_id = {}
    
    for space in filtered_spaces:
        # Get basic properties
        space_data = {
            'id': space.id(),
            'name': space.Name or 'Unnamed',
            'long_name': space.LongName or '',
            'object_type': space.ObjectType or '',
            'level': None,
            'properties': {},
            'quantities': {},
            'bounding_elements': [],
            'confidence_level': 'high'
        }
        
        # Get container (level)
        container = ifcopenshell.util.element.get_container(space)
        if container:
            space_data['level'] = container.Name or 'Unnamed'
        
        # Get all property sets
        psets = ifcopenshell.util.element.get_psets(space)
        space_data['properties'] = psets
        
        # Extract key quantities
        if 'BaseQuantities' in psets:
            quantities = psets['BaseQuantities']
            space_data['quantities'] = {
                'area': quantities.get('NetFloorArea', quantities.get('GrossFloorArea', 0)),
                'volume': quantities.get('NetVolume', quantities.get('GrossVolume', 0)),
                'height': quantities.get('Height', quantities.get('ClearHeight', 0)),
                'perimeter': quantities.get('NetPerimeter', quantities.get('GrossPerimeter', 0)),
                'ceiling_height': quantities.get('FinishCeilingHeight', quantities.get('ClearHeight', 0))
            }
        
        # Get bounding elements for spatial analysis
        if hasattr(space, 'BoundedBy') and space.BoundedBy:
            for rel in space.BoundedBy:
                if hasattr(rel, 'RelatedBuildingElement') and rel.RelatedBuildingElement:
                    element = rel.RelatedBuildingElement
                    space_data['bounding_elements'].append({
                        'id': element.id(),
                        'name': element.Name or 'Unnamed',
                        'type': element.is_a()
                    })
        
        spaces_data.append(space_data)
        space_by_id[space.id()] = space_data
    
    result['spaces_found'] = spaces_data
    
    # Generate layout summary
    if spaces_data:
        # Count spaces by level and type
        level_counts = {}
        total_area = 0
        total_volume = 0
        
        for space in spaces_data:
            level = space['level'] or 'Unknown'
            level_counts[level] = level_counts.get(level, 0) + 1
            total_area += space['quantities'].get('area', 0)
            total_volume += space['quantities'].get('volume', 0)
        
        result['layout_summary'] = {
            'total_spaces': len(spaces_data),
            'spaces_by_level': level_counts,
            'total_floor_area': total_area,
            'total_volume': total_volume,
            'average_area': total_area / len(spaces_data) if spaces_data else 0,
            'space_types': list(set([s['long_name'] for s in spaces_data if s['long_name']]))
        }
    
    # Analyze spatial relationships
    if spatial_analysis and spaces_data:
        spatial_relationships = {}
        
        # Find shared bounding elements between spaces
        for i, space1 in enumerate(spaces_data):
            space1_name = space1['name']
            spatial_relationships[space1_name] = {
                'adjacent_spaces': [],
                'connecting_elements': [],
                'separating_elements': []
            }
            
            # Get bounding elements of this space
            space1_elements = set([elem['id'] for elem in space1['bounding_elements']])
            
            for j, space2 in enumerate(spaces_data):
                if i >= j:  # Avoid duplicates and self-comparison
                    continue
                
                space2_name = space2['name']
                space2_elements = set([elem['id'] for elem in space2['bounding_elements']])
                
                # Find shared elements
                shared_elements = space1_elements.intersection(space2_elements)
                
                if shared_elements:
                    # Spaces are adjacent
                    spatial_relationships[space1_name]['adjacent_spaces'].append(space2_name)
                    spatial_relationships[space1_name]['separating_elements'].extend(list(shared_elements))
                    
                    # Add reverse relationship
                    if space2_name not in spatial_relationships:
                        spatial_relationships[space2_name] = {
                            'adjacent_spaces': [],
                            'connecting_elements': [],
                            'separating_elements': []
                        }
                    spatial_relationships[space2_name]['adjacent_spaces'].append(space1_name)
                    spatial_relationships[space2_name]['separating_elements'].extend(list(shared_elements))
        
        # Find connecting elements (doors, windows)
        doors = model.by_type('IfcDoor')
        windows = model.by_type('IfcWindow')
        
        for door in doors:
            door_name = door.Name or 'Unnamed'
            door_id = door.id()
            
            # Check which spaces this door connects
            connected_spaces = []
            for space in spaces_data:
                for elem in space['bounding_elements']:
                    if elem['id'] == door_id:
                        connected_spaces.append(space['name'])
                        break
            
            if len(connected_spaces) >= 2:
                for space_name in connected_spaces:
                    if space_name in spatial_relationships:
                        spatial_relationships[space_name]['connecting_elements'].append({
                            'id': door_id,
                            'name': door_name,
                            'type': 'IfcDoor',
                            'connects_to': [s for s in connected_spaces if s != space_name]
                        })
        
        result['spatial_relationships'] = spatial_relationships
    
    # Analyze fire ratings
    if include_fire_ratings:
        fire_rating_analysis = {
            'walls_with_fire_ratings': [],
            'doors_with_fire_ratings': [],
            'fire_separating_elements': [],
            'confidence_level': 'medium'  # ArchiCAD models often have limited fire rating data
        }
        
        # Check walls for fire ratings
        walls = model.by_type('IfcWall')
        for wall in walls:
            wall_psets = ifcopenshell.util.element.get_psets(wall)
            wall_data = {
                'id': wall.id(),
                'name': wall.Name or 'Unnamed',
                'fire_rating': None,
                'fire_properties': {}
            }
            
            # Look for fire-related properties
            for pset_name, pset_data in wall_psets.items():
                if 'fire' in pset_name.lower():
                    wall_data['fire_properties'][pset_name] = pset_data
                    
                    # Extract fire rating
                    for prop_name, prop_value in pset_data.items():
                        if 'rating' in prop_name.lower() or 'resistance' in prop_name.lower():
                            wall_data['fire_rating'] = prop_value
                            break
            
            if wall_data['fire_rating'] or wall_data['fire_properties']:
                fire_rating_analysis['walls_with_fire_ratings'].append(wall_data)
        
        # Check doors for fire ratings
        doors = model.by_type('IfcDoor')
        for door in doors:
            door_psets = ifcopenshell.util.element.get_psets(door)
            door_data = {
                'id': door.id(),
                'name': door.Name or 'Unnamed',
                'fire_rating': None,
                'fire_properties': {}
            }
            
            # Look for fire-related properties
            for pset_name, pset_data in door_psets.items():
                if 'fire' in pset_name.lower():
                    door_data['fire_properties'][pset_name] = pset_data
                    
                    # Extract fire rating
                    for prop_name, prop_value in pset_data.items():
                        if 'rating' in prop_name.lower() or 'resistance' in prop_name.lower():
                            door_data['fire_rating'] = prop_value
                            break
            
            if door_data['fire_rating'] or door_data['fire_properties']:
                fire_rating_analysis['doors_with_fire_ratings'].append(door_data)
        
        # Identify fire separating elements between spaces
        if spatial_analysis and result['spatial_relationships']:
            for space_name, rel_data in result['spatial_relationships'].items():
                for element_id in rel_data['separating_elements']:
                    # Check if this element has fire rating
                    element = model[element_id]
                    if element:
                        element_psets = ifcopenshell.util.element.get_psets(element)
                        for pset_name, pset_data in element_psets.items():
                            if 'fire' in pset_name.lower():
                                fire_rating_analysis['fire_separating_elements'].append({
                                    'element_id': element_id,
                                    'element_name': element.Name or 'Unnamed',
                                    'element_type': element.is_a(),
                                    'separates_spaces': [space_name] + rel_data['adjacent_spaces'],
                                    'fire_properties': pset_data
                                })
                                break
        
        result['fire_rating_analysis'] = fire_rating_analysis
    
    # Identify separating elements
    if spatial_analysis:
        all_separating_elements = set()
        for space in spaces_data:
            for elem in space['bounding_elements']:
                all_separating_elements.add(elem['id'])
        
        separating_elements = []
        for elem_id in all_separating_elements:
            element = model[elem_id]
            if element:
                elem_data = {
                    'id': elem_id,
                    'name': element.Name or 'Unnamed',
                    'type': element.is_a(),
                    'bounds_spaces': []
                }
                
                # Find which spaces this element bounds
                for space in spaces_data:
                    for space_elem in space['bounding_elements']:
                        if space_elem['id'] == elem_id:
                            elem_data['bounds_spaces'].append(space['name'])
                            break
                
                separating_elements.append(elem_data)
        
        result['separating_elements'] = separating_elements
    
    # Generate natural language description
    description_parts = []
    
    if spaces_data:
        description_parts.append(f"The model contains {len(spaces_data)} spaces")
        
        if result['layout_summary'].get('spaces_by_level'):
            level_info = []
            for level, count in result['layout_summary']['spaces_by_level'].items():
                level_info.append(f"{count} on {level}")
            description_parts.append(f"distributed across levels: {', '.join(level_info)}")
        
        total_area = result['layout_summary'].get('total_floor_area', 0)
        if total_area > 0:
            description_parts.append(f"with a total floor area of {total_area:.2f} m²")
        
        # List space types
        space_types = result['layout_summary'].get('space_types', [])
        if space_types:
            description_parts.append(f"Space types include: {', '.join(space_types)}")
        
        # Spatial relationships
        if spatial_analysis and result['spatial_relationships']:
            adjacencies = []
            for space_name, rel_data in result['spatial_relationships'].items():
                if rel_data['adjacent_spaces']:
                    adjacencies.append(f"{space_name} connects to {', '.join(rel_data['adjacent_spaces'])}")
            
            if adjacencies:
                description_parts.append(f"Spatial connections: {'; '.join(adjacencies[:3])}")
        
        # Fire rating information
        if include_fire_ratings and result['fire_rating_analysis']:
            fire_walls = len(result['fire_rating_analysis'].get('walls_with_fire_ratings', []))
            fire_doors = len(result['fire_rating_analysis'].get('doors_with_fire_ratings', []))
            
            if fire_walls > 0 or fire_doors > 0:
                description_parts.append(f"Fire safety: {fire_walls} walls and {fire_doors} doors with fire rating properties found")
            else:
                description_parts.append("Limited fire rating information available in the model")
    
    result['layout_description'] = '. '.join(description_parts) + '.'
    
    return result