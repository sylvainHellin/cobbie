import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def analyze_systems_by_building_level(
    ifc_file: ifcopenshell.file,
    level_name: str,
    element_types: Optional[List[str]] = None,
    group_by_field: str = 'ObjectType',
    include_examples: int = 2,
    case_sensitive: bool = False,
    return_system_details: bool = True
) -> Dict[str, Any]:
    """
    Analyzes systems and components on a specific building level by examining multiple element types,
    grouping them by system identifiers, and providing component counts with examples.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        level_name: Name of the building storey to analyze (e.g., 'Roof', 'Level 1', '03 Third Floor')
        element_types: List of IFC element types to check (defaults to common MEP types if None)
        group_by_field: Field to group elements by (default 'ObjectType', alternatives: 'Name', 'Description')
        include_examples: Number of example elements to include per group (default 2)
        case_sensitive: Whether string matching should be case sensitive (default False)
        return_system_details: Whether to include detailed element information (default True)
    
    Returns:
        Dict containing level info, system breakdown with counts, examples, and summary statistics.
        
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = analyze_systems_by_building_level(model, 'Roof')
        >>> print(f"Found {result['summary']['total_elements']} elements on {result['level_info']['name']}")
    """
    try:
        # Default element types for MEP analysis if not provided
        if element_types is None:
            element_types = [
                'IfcDistributionElement', 'IfcFlowSegment', 'IfcFlowTerminal', 
                'IfcFlowController', 'IfcFlowMovingDevice', 'IfcFlowStorageDevice',
                'IfcEnergyConversionDevice', 'IfcDistributionControlElement'
            ]
        
        # Find the target building level
        target_level = None
        levels = ifc_file.by_type('IfcBuildingStorey')
        
        for level in levels:
            level_name_match = level.Name if hasattr(level, 'Name') else ''
            if case_sensitive:
                if level_name_match == level_name:
                    target_level = level
                    break
            else:
                if level_name_match.lower() == level_name.lower():
                    target_level = level
                    break
        
        if target_level is None:
            return {
                'success': False,
                'error': f'Building level "{level_name}" not found',
                'available_levels': [getattr(level, 'Name', 'N/A') for level in levels]
            }
        
        # Initialize results structure
        results = {
            'success': True,
            'level_info': {
                'name': getattr(target_level, 'Name', 'N/A'),
                'elevation': getattr(target_level, 'Elevation', 'N/A')
            },
            'systems': {},
            'summary': {
                'total_elements': 0,
                'total_systems': 0,
                'element_types_found': []
            }
        }
        
        # Analyze each element type
        for elem_type in element_types:
            try:
                elements = ifc_file.by_type(elem_type)
                if not elements:
                    continue
                
                # Filter elements on the target level
                level_elements = []
                for elem in elements:
                    try:
                        container = ifcopenshell.util.element.get_container(elem)
                        if container == target_level:
                            level_elements.append(elem)
                    except:
                        # Fallback to manual containment check
                        if hasattr(elem, 'ContainedInStructure'):
                            for rel in elem.ContainedInStructure:
                                if hasattr(rel, 'RelatingStructure') and rel.RelatingStructure == target_level:
                                    level_elements.append(elem)
                                    break
                
                if level_elements:
                    results['summary']['element_types_found'].append(elem_type)
                    
                    # Group elements by the specified field
                    groups = {}
                    for elem in level_elements:
                        group_value = getattr(elem, group_by_field, 'Unknown')
                        if group_value is None:
                            group_value = 'Unknown'
                        
                        if group_value not in groups:
                            groups[group_value] = {
                                'count': 0,
                                'elements': [],
                                'element_type': elem_type
                            }
                        
                        groups[group_value]['count'] += 1
                        groups[group_value]['elements'].append(elem)
                    
                    # Add groups to results
                    for group_name, group_data in groups.items():
                        system_key = f"{elem_type}:{group_name}"
                        
                        system_info = {
                            'element_type': elem_type,
                            'group_name': group_name,
                            'count': group_data['count']
                        }
                        
                        # Add examples if requested
                        if include_examples > 0 and return_system_details:
                            examples = []
                            for i, elem in enumerate(group_data['elements'][:include_examples]):
                                example_info = {
                                    'name': getattr(elem, 'Name', 'N/A'),
                                    'id': elem.id()
                                }
                                examples.append(example_info)
                            system_info['examples'] = examples
                        
                        results['systems'][system_key] = system_info
                        results['summary']['total_elements'] += group_data['count']
                    
            except Exception as e:
                # Skip element types that don't exist in this schema
                continue
        
        results['summary']['total_systems'] = len(results['systems'])
        
        return results
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Analysis failed: {str(e)}'
        }