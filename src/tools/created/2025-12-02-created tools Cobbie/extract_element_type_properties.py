import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def extract_element_type_properties(
    ifc_file: ifcopenshell.file,
    element_type: str,
    level_filter: Optional[List[str]] = None,
    include_empty_properties: bool = False,
    property_sets_filter: Optional[List[str]] = None,
    max_elements: int = 10,
    group_by_type_definition: bool = True
) -> Dict[str, Any]:
    """
    Comprehensively extracts all property information for elements of a specific IFC type.
    
    Args:
        ifc_file: The loaded IFC model
        element_type: IFC element type to analyze (e.g., 'IfcRoof', 'IfcWall', 'IfcDoor')
        level_filter: Optional list of building level names to filter elements
        include_empty_properties: Whether to include properties with placeholder/default values
        property_sets_filter: Optional list of property set names to prioritize
        max_elements: Maximum number of elements to analyze in detail
        group_by_type_definition: Whether to group results by type definitions
    
    Returns:
        Dict with comprehensive element property analysis including:
        - summary: Total count, type definitions found, levels found
        - elements: List of detailed element information
        - property_analysis: Summary of available property sets and properties
        - type_definitions: Grouping by type definitions with counts
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> roof_analysis = extract_element_type_properties(model, 'IfcRoof')
        >>> print(f"Found {roof_analysis['summary']['total_count']} roof elements")
        >>> for element in roof_analysis['elements']:
        ...     print(f"Roof: {element['name']}")
        ...     if 'Pset_RoofCommon' in element['property_sets']:
        ...         print(f"  Type: {element['property_sets']['Pset_RoofCommon'].get('Reference')}")
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        if not elements:
            return {
                'summary': {'total_count': 0, 'type_definitions': [], 'levels_found': []},
                'elements': [],
                'property_analysis': {'property_sets': {}, 'properties': {}},
                'type_definitions': {}
            }
        
        # Filter by level if specified
        if level_filter:
            filtered_elements = []
            for element in elements:
                try:
                    container = ifcopenshell.util.element.get_container(element)
                    if container and container.Name in level_filter:
                        filtered_elements.append(element)
                except:
                    continue
            elements = filtered_elements
        
        # Limit number of elements to analyze
        elements_to_analyze = elements[:max_elements]
        
        # Initialize result structures
        result = {
            'summary': {
                'total_count': len(elements),
                'type_definitions': [],
                'levels_found': []
            },
            'elements': [],
            'property_analysis': {
                'property_sets': {},
                'properties': {}
            },
            'type_definitions': {}
        }
        
        # Process each element
        for element in elements_to_analyze:
            try:
                # Get basic attributes
                element_info = {
                    'id': element.id(),
                    'name': element.Name,
                    'object_type': getattr(element, 'ObjectType', None),
                    'description': getattr(element, 'Description', None),
                    'predefined_type': getattr(element, 'PredefinedType', None)
                }
                
                # Get container/level information
                try:
                    container = ifcopenshell.util.element.get_container(element)
                    if container:
                        element_info['container'] = {
                            'name': container.Name,
                            'type': container.is_a(),
                            'id': container.id()
                        }
                        if container.Name not in result['summary']['levels_found']:
                            result['summary']['levels_found'].append(container.Name)
                except:
                    element_info['container'] = None
                
                # Get type definition information
                type_def = None
                for rel in element.IsDefinedBy:
                    if rel.is_a('IfcRelDefinesByType'):
                        type_def = rel.RelatingType
                        break
                
                if type_def:
                    element_info['type_definition'] = {
                        'name': type_def.Name,
                        'type': type_def.is_a(),
                        'id': type_def.id()
                    }
                    type_name = type_def.Name or 'Unknown'
                    if type_name not in result['type_definitions']:
                        result['type_definitions'][type_name] = {
                            'count': 0,
                            'elements': []
                        }
                    result['type_definitions'][type_name]['count'] += 1
                    result['type_definitions'][type_name]['elements'].append(element_info['id'])
                
                # Get all property sets
                element_info['property_sets'] = {}
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    
                    for pset_name, pset_data in psets.items():
                        # Filter property sets if specified
                        if property_sets_filter and pset_name not in property_sets_filter:
                            continue
                        
                        # Process properties in the set
                        processed_properties = {}
                        for prop_name, prop_value in pset_data.items():
                            # Skip empty properties if not requested
                            if not include_empty_properties:
                                if (prop_value is None or 
                                    (isinstance(prop_value, str) and prop_value.strip() == '') or
                                    (hasattr(prop_value, 'wrappedValue') and prop_value.wrappedValue is None)):
                                    continue
                            
                            # Convert IFC values to Python primitives
                            if hasattr(prop_value, 'wrappedValue'):
                                processed_properties[prop_name] = prop_value.wrappedValue
                            else:
                                processed_properties[prop_name] = prop_value
                        
                        if processed_properties:  # Only add if there are properties
                            element_info['property_sets'][pset_name] = processed_properties
                            
                            # Update property analysis
                            if pset_name not in result['property_analysis']['property_sets']:
                                result['property_analysis']['property_sets'][pset_name] = {
                                    'count': 0,
                                    'properties': set()
                                }
                            result['property_analysis']['property_sets'][pset_name]['count'] += 1
                            
                            for prop_name in processed_properties.keys():
                                if prop_name not in result['property_analysis']['properties']:
                                    result['property_analysis']['properties'][prop_name] = {
                                        'count': 0,
                                        'property_sets': set()
                                    }
                                result['property_analysis']['properties'][prop_name]['count'] += 1
                                result['property_analysis']['properties'][prop_name]['property_sets'].add(pset_name)
                
                except Exception as e:
                    element_info['property_sets'] = {'error': str(e)}
                
                result['elements'].append(element_info)
                
            except Exception as e:
                # Add error element info but continue processing
                result['elements'].append({
                    'id': getattr(element, 'id', lambda: 'unknown')(),
                    'error': str(e)
                })
        
        # Update summary with type definitions
        result['summary']['type_definitions'] = list(result['type_definitions'].keys())
        
        # Convert sets to lists for JSON serialization
        for pset_info in result['property_analysis']['property_sets'].values():
            pset_info['properties'] = list(pset_info['properties'])
        
        for prop_info in result['property_analysis']['properties'].values():
            prop_info['property_sets'] = list(prop_info['property_sets'])
        
        return result
        
    except Exception as e:
        return {
            'error': f'Failed to extract element properties: {str(e)}',
            'summary': {'total_count': 0, 'type_definitions': [], 'levels_found': []},
            'elements': [],
            'property_analysis': {'property_sets': {}, 'properties': {}},
            'type_definitions': {}
        }