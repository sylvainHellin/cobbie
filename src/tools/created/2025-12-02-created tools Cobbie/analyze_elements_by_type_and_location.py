import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any

def analyze_elements_by_type_and_location(
    ifc_file: ifcopenshell.file,
    element_type: str,
    include_properties: bool = True,
    include_spatial: bool = True,
    property_sets_filter: Optional[List[str]] = None,
    max_elements: int = 100,
    group_by_level: bool = True,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes IFC elements by type, providing comprehensive information about their properties,
    spatial distribution across building levels, and basic characteristics.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcRailing', 'IfcDoor', 'IfcWindow')
        include_properties: Whether to extract property set information (default True)
        include_spatial: Whether to analyze spatial relationships and building level distribution (default True)
        property_sets_filter: Optional list of property set names to prioritize (default None for all)
        max_elements: Maximum number of elements to analyze in detail (default 100)
        group_by_level: Whether to group results by building level (default True)
        case_sensitive: Whether string matching should be case sensitive (default False)
    
    Returns:
        Dict containing:
        - total_count: Total number of elements found
        - elements_by_level: Distribution of elements across building levels
        - element_details: List of detailed element information including properties
        - summary: Basic statistics and overview
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = analyze_elements_by_type_and_location(model, 'IfcRailing')
        >>> print(f"Found {result['total_count']} railings")
    """
    
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_count = len(elements)
        
        # Initialize result structure
        result = {
            'total_count': total_count,
            'elements_by_level': {},
            'element_details': [],
            'summary': {
                'element_type': element_type,
                'analyzed_count': min(total_count, max_elements),
                'has_properties': False,
                'has_spatial_info': False,
                'unique_levels': set()
            }
        }
        
        # Process each element
        for i, element in enumerate(elements[:max_elements]):
            element_info = {
                'id': element.GlobalId,
                'name': element.Name,
                'object_type': getattr(element, 'ObjectType', None),
                'description': getattr(element, 'Description', None),
                'properties': {},
                'spatial_info': {}
            }
            
            # Extract properties if requested
            if include_properties:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    if psets:
                        result['summary']['has_properties'] = True
                        
                        # Filter property sets if filter is provided
                        if property_sets_filter:
                            for pset_name in property_sets_filter:
                                if pset_name in psets:
                                    element_info['properties'][pset_name] = psets[pset_name]
                        else:
                            element_info['properties'] = psets
                except Exception as e:
                    element_info['properties'] = {'error': str(e)}
            
            # Extract spatial information if requested
            if include_spatial:
                try:
                    container = ifcopenshell.util.element.get_container(element)
                    if container:
                        result['summary']['has_spatial_info'] = True
                        level_name = container.Name if container.Name else 'Unknown'
                        element_info['spatial_info'] = {
                            'container_type': container.is_a(),
                            'container_name': level_name,
                            'container_id': container.GlobalId
                        }
                        
                        # Group by level
                        if group_by_level:
                            if level_name not in result['elements_by_level']:
                                result['elements_by_level'][level_name] = []
                            result['elements_by_level'][level_name].append(element_info)
                            
                            result['summary']['unique_levels'].add(level_name)
                except Exception as e:
                    element_info['spatial_info'] = {'error': str(e)}
            
            # Add to element details if not grouping by level or if grouping failed
            if not group_by_level or not include_spatial:
                result['element_details'].append(element_info)
        
        # Convert set to list for JSON serialization
        result['summary']['unique_levels'] = list(result['summary']['unique_levels'])
        
        # If grouping by level, move element details to level groups
        if group_by_level and include_spatial:
            # Count elements per level
            for level_name in result['elements_by_level']:
                result['elements_by_level'][level_name] = {
                    'count': len(result['elements_by_level'][level_name]),
                    'elements': result['elements_by_level'][level_name]
                }
        
        return result
        
    except Exception as e:
        return {
            'error': f"Failed to analyze elements: {str(e)}",
            'total_count': 0,
            'elements_by_level': {},
            'element_details': [],
            'summary': {'error': str(e)}
        }