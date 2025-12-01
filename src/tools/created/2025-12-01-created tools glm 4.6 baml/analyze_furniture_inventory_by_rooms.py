import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union
import re

def analyze_furniture_inventory_by_rooms(
    ifc_file: ifcopenshell.file,
    furniture_element_types: List[str] = ['IfcFurnishingElement'],
    furniture_type_mapping: Optional[Dict[str, List[str]]] = None,
    room_identifier_pattern: str = 'first_part_before_underscore',
    room_type_inference_rules: Optional[Dict[str, Dict[str, Union[List[str], int]]]] = None,
    include_property_sets: bool = True,
    max_examples_per_category: int = 3,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes furniture elements in an IFC model and provides comprehensive inventory categorized by furniture type and room distribution.
    
    This function handles the common BIM challenge where furniture lacks proper spatial containment relationships
    by using naming patterns to infer room assignments and semantic analysis to categorize furniture types.
    It also infers room types based on furniture composition patterns.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        furniture_element_types: List of IFC types to search for furniture (default: ['IfcFurnishingElement'])
        furniture_type_mapping: Dict mapping furniture types to keyword lists for categorization
            (default includes common categories like 'toilet', 'kitchen', 'sink', etc.)
        room_identifier_pattern: Pattern to extract room IDs from furniture names
            (default: 'first_part_before_underscore')
        room_type_inference_rules: Dict mapping furniture composition patterns to room types
            (default includes bathroom, kitchen, utility room patterns)
        include_property_sets: Boolean to include property set analysis (default: True)
        max_examples_per_category: Maximum example elements to include per category (default: 3)
        case_sensitive: Boolean for case-sensitive keyword matching (default: False)
    
    Returns:
        Dict containing:
        - total_furniture_count: Total number of furniture elements found
        - furniture_by_type: Dict of furniture types with counts and examples
        - furniture_by_room: Dict of room identifiers with their furniture inventories
        - inferred_room_types: Dict of room types inferred from furniture composition
        - spatial_assignment_analysis: Analysis of spatial containment completeness
        - summary_statistics: Overall inventory statistics and distributions
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_furniture_inventory_by_rooms(model)
        >>> print(f"Total furniture: {result['total_furniture_count']}")
        >>> print(f"Furniture types: {list(result['furniture_by_type'].keys())}")
    """
    
    try:
        # Default furniture type mapping if not provided
        if furniture_type_mapping is None:
            furniture_type_mapping = {
                'Toilet': ['toilet'],
                'Dryer': ['droger', 'dryer', 'washing machine', 'wasmaschine'],
                'Kitchen Block': ['keuken', 'kitchen', 'kook', 'cook'],
                'Corner Sink': ['hoekfontein', 'corner sink', 'corner basin'],
                'Technical Cabinet': ['techniekkast', 'technical cabinet', 'utility cabinet'],
                'Washbasin': ['wastafel', 'washbasin', 'sink', 'basin'],
                'Flower Box': ['bloembak', 'flower box', 'planter'],
                'Electrical Cabinet': ['elektrakast', 'electrical cabinet', 'switchboard'],
                'Bed': ['bed', 'slaap', 'sleep'],
                'Table': ['table', 'tafel', 'desk'],
                'Chair': ['chair', 'stoel', 'seat'],
                'Wardrobe': ['wardrobe', 'kast', 'closet', 'kledingkast'],
                'Shower': ['shower', 'douche'],
                'Bathtub': ['bathtub', 'bad', 'badkuip']
            }
        
        # Default room type inference rules if not provided
        if room_type_inference_rules is None:
            room_type_inference_rules = {
                'Bathroom': {
                    'required_types': ['toilet'],
                    'optional_types': ['washbasin', 'corner sink', 'shower', 'bathtub'],
                    'min_required': 1
                },
                'Kitchen': {
                    'required_types': ['kitchen block'],
                    'optional_types': [],
                    'min_required': 1
                },
                'Laundry/Utility Room': {
                    'required_types': ['dryer'],
                    'optional_types': ['technical cabinet', 'washbasin'],
                    'min_required': 1
                },
                'Technical/Utility Room': {
                    'required_types': ['technical cabinet', 'electrical cabinet'],
                    'optional_types': [],
                    'min_required': 1
                },
                'Bedroom': {
                    'required_types': ['bed'],
                    'optional_types': ['wardrobe', 'table', 'chair'],
                    'min_required': 1
                },
                'Living Room': {
                    'required_types': ['table', 'chair'],
                    'optional_types': ['wardrobe'],
                    'min_required': 2
                },
                'Outdoor/Balcony Space': {
                    'required_types': ['flower box'],
                    'optional_types': [],
                    'min_required': 1
                }
            }
        
        # Initialize result structure
        result = {
            'total_furniture_count': 0,
            'furniture_by_type': {},
            'furniture_by_room': {},
            'inferred_room_types': {},
            'spatial_assignment_analysis': {},
            'summary_statistics': {}
        }
        
        # Collect all furniture elements
        all_furniture = []
        for element_type in furniture_element_types:
            try:
                elements = ifc_file.by_type(element_type)
                all_furniture.extend(elements)
            except Exception as e:
                print(f"Warning: Could not retrieve elements of type {element_type}: {e}")
                continue
        
        result['total_furniture_count'] = len(all_furniture)
        
        if result['total_furniture_count'] == 0:
            return result
        
        # Analyze spatial containment in detail
        space_assigned = 0
        storey_assigned = 0
        building_assigned = 0
        unassigned = 0
        container_types = {}
        
        for furniture in all_furniture:
            container = ifcopenshell.util.element.get_container(furniture)
            if container:
                container_type = container.is_a()
                if container_type not in container_types:
                    container_types[container_type] = 0
                container_types[container_type] += 1
                
                if container_type == 'IfcSpace':
                    space_assigned += 1
                elif container_type == 'IfcBuildingStorey':
                    storey_assigned += 1
                elif container_type == 'IfcBuilding':
                    building_assigned += 1
            else:
                unassigned += 1
        
        result['spatial_assignment_analysis'] = {
            'total_elements': result['total_furniture_count'],
            'space_assigned': space_assigned,
            'storey_assigned': storey_assigned,
            'building_assigned': building_assigned,
            'unassigned': unassigned,
            'container_types': container_types,
            'proper_space_assignment_percentage': (space_assigned / result['total_furniture_count']) * 100 if result['total_furniture_count'] > 0 else 0,
            'any_spatial_assignment_percentage': ((space_assigned + storey_assigned + building_assigned) / result['total_furniture_count']) * 100 if result['total_furniture_count'] > 0 else 0
        }
        
        # Categorize furniture by type
        furniture_by_type = {}
        room_furniture_mapping = {}
        
        for furniture in all_furniture:
            name = furniture.Name or ''
            if not case_sensitive:
                name_lower = name.lower()
            else:
                name_lower = name
            
            # Categorize furniture type
            furniture_type = 'Other'
            for ftype, keywords in furniture_type_mapping.items():
                for keyword in keywords:
                    if not case_sensitive:
                        keyword_lower = keyword.lower()
                    else:
                        keyword_lower = keyword
                    
                    if keyword_lower in name_lower:
                        furniture_type = ftype
                        break
                if furniture_type != 'Other':
                    break
            
            # Add to furniture type categorization
            if furniture_type not in furniture_by_type:
                furniture_by_type[furniture_type] = {
                    'count': 0,
                    'examples': [],
                    'elements': []
                }
            
            furniture_by_type[furniture_type]['count'] += 1
            furniture_by_type[furniture_type]['elements'].append(furniture)
            
            if len(furniture_by_type[furniture_type]['examples']) < max_examples_per_category:
                example_data = {
                    'id': furniture.id,
                    'Name': furniture.Name,
                    'ObjectType': furniture.ObjectType,
                    'GlobalId': furniture.GlobalId
                }
                
                if include_property_sets:
                    try:
                        psets = ifcopenshell.util.element.get_psets(furniture)
                        example_data['property_sets'] = psets
                    except Exception:
                        example_data['property_sets'] = {}
                
                furniture_by_type[furniture_type]['examples'].append(example_data)
            
            # Extract room identifier
            room_id = 'Unknown'
            if room_identifier_pattern == 'first_part_before_underscore':
                if '_' in name:
                    room_id = name.split('_')[0]
                else:
                    room_id = 'No_Room_ID'
            else:
                # Allow custom regex patterns
                try:
                    match = re.search(room_identifier_pattern, name)
                    if match:
                        room_id = match.group(1) if match.groups() else match.group(0)
                except Exception:
                    room_id = 'Pattern_Error'
            
            # Add to room mapping
            if room_id not in room_furniture_mapping:
                room_furniture_mapping[room_id] = {
                    'count': 0,
                    'furniture_types': {},
                    'elements': []
                }
            
            room_furniture_mapping[room_id]['count'] += 1
            room_furniture_mapping[room_id]['elements'].append(furniture)
            
            if furniture_type not in room_furniture_mapping[room_id]['furniture_types']:
                room_furniture_mapping[room_id]['furniture_types'][furniture_type] = 0
            room_furniture_mapping[room_id]['furniture_types'][furniture_type] += 1
        
        result['furniture_by_type'] = furniture_by_type
        result['furniture_by_room'] = room_furniture_mapping
        
        # Infer room types based on furniture composition
        inferred_room_types = {}
        
        for room_id, room_data in room_furniture_mapping.items():
            room_furniture_types = room_data['furniture_types']
            inferred_type = 'Unknown'
            confidence = 0
            
            for room_type, rules in room_type_inference_rules.items():
                match_score = 0
                
                # Check required types
                required_matches = 0
                for req_type in rules['required_types']:
                    if req_type.lower() in [ft.lower() for ft in room_furniture_types.keys()]:
                        required_matches += 1
                
                if required_matches >= rules['min_required']:
                    match_score += required_matches * 10
                    
                    # Check optional types for additional confidence
                    for opt_type in rules['optional_types']:
                        if opt_type.lower() in [ft.lower() for ft in room_furniture_types.keys()]:
                            match_score += 2
                    
                    if match_score > confidence:
                        confidence = match_score
                        inferred_type = room_type
            
            inferred_room_types[room_id] = {
                'inferred_type': inferred_type,
                'confidence': confidence,
                'furniture_composition': room_furniture_types,
                'total_items': room_data['count']
            }
        
        result['inferred_room_types'] = inferred_room_types
        
        # Generate summary statistics
        total_types = len(furniture_by_type)
        total_rooms = len(room_furniture_mapping)
        
        # Calculate percentages
        type_percentages = {}
        for ftype, data in furniture_by_type.items():
            percentage = (data['count'] / result['total_furniture_count']) * 100
            type_percentages[ftype] = round(percentage, 1)
        
        # Room type distribution
        room_type_counts = {}
        for room_data in inferred_room_types.values():
            room_type = room_data['inferred_type']
            if room_type not in room_type_counts:
                room_type_counts[room_type] = 0
            room_type_counts[room_type] += 1
        
        result['summary_statistics'] = {
            'total_furniture_types': total_types,
            'total_rooms_identified': total_rooms,
            'furniture_type_percentages': type_percentages,
            'room_type_distribution': room_type_counts,
            'most_common_furniture_type': max(furniture_by_type.items(), key=lambda x: x[1]['count'])[0] if furniture_by_type else None,
            'largest_room': max(room_furniture_mapping.items(), key=lambda x: x[1]['count'])[0] if room_furniture_mapping else None
        }
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'total_furniture_count': 0,
            'furniture_by_type': {},
            'furniture_by_room': {},
            'inferred_room_types': {},
            'spatial_assignment_analysis': {},
            'summary_statistics': {}
        }