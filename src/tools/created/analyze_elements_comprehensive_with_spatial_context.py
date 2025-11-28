import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def analyze_elements_comprehensive_with_spatial_context(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_keywords: Optional[List[str]] = None,
    spatial_container_types: Optional[List[str]] = None,
    aggregation_fields: Optional[List[str]] = None,
    include_details: bool = True,
    include_spatial_analysis: bool = True,
    max_elements: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyzes IFC elements of a specified type with comprehensive property extraction, 
    spatial context analysis, and aggregated summarization.
    
    This function implements a complete workflow for element analysis: discovery by type, 
    property extraction, spatial container determination, and multi-dimensional aggregation. 
    It answers questions like 'what are all the railings/doors/windows in the building, 
    their properties, and where are they installed?'
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcRailing', 'IfcDoor', 'IfcWindow')
        property_keywords: Optional list of keywords to highlight in property output 
                          (e.g., ['Height', 'Width', 'Area'])
        spatial_container_types: List of spatial container types to search for 
                                 (default: ['IfcBuildingStorey'])
        aggregation_fields: List of property names to aggregate by 
                           (default: ['Height', 'ObjectType'])
        include_details: Boolean to include individual element details (default: True)
        include_spatial_analysis: Boolean to determine spatial containers (default: True)
        max_elements: Optional limit on elements to analyze (default: None for all)
    
    Returns:
        Dict containing:
        'summary': Totals and aggregated statistics
        'elements': List of detailed element information
        'spatial_distribution': Elements grouped by location
        'property_analysis': Aggregated data by specified fields
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_elements_comprehensive_with_spatial_context(
        ...     model, 'IfcRailing', 
        ...     property_keywords=['Height'],
        ...     aggregation_fields=['Height', 'ObjectType']
        ... )
        >>> print(f"Found {result['summary']['total_elements']} railings")
    """
    
    # Set defaults
    if property_keywords is None:
        property_keywords = []
    if spatial_container_types is None:
        spatial_container_types = ['IfcBuildingStorey']
    if aggregation_fields is None:
        aggregation_fields = ['Height', 'ObjectType']
    
    # Initialize result structure
    result = {
        'summary': {
            'total_elements': 0,
            'elements_with_properties': 0,
            'elements_with_spatial_context': 0
        },
        'elements': [],
        'spatial_distribution': {},
        'property_analysis': {}
    }
    
    try:
        # Get elements by type
        elements = ifc_file.by_type(element_type)
        
        # Apply limit if specified
        if max_elements is not None:
            elements = elements[:max_elements]
        
        result['summary']['total_elements'] = len(elements)
        
        # Process each element
        for element in elements:
            element_info = {
                'id': element.id,
                'guid': element.GlobalId,
                'name': element.Name,
                'object_type': element.ObjectType,
                'element_type': element.is_a(),
                'properties': {},
                'spatial_context': None,
                'highlighted_properties': {}
            }
            
            # Get basic element info
            try:
                basic_info = element.get_info()
                element_info['basic_info'] = basic_info
            except:
                element_info['basic_info'] = {}
            
            # Extract properties
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                element_info['properties'] = psets
                
                if psets:
                    result['summary']['elements_with_properties'] += 1
                    
                    # Highlight specified keywords
                    for keyword in property_keywords:
                        keyword_lower = keyword.lower()
                        for pset_name, pset_data in psets.items():
                            if isinstance(pset_data, dict):
                                for prop_name, prop_value in pset_data.items():
                                    if keyword_lower in prop_name.lower():
                                        if keyword not in element_info['highlighted_properties']:
                                            element_info['highlighted_properties'][keyword] = []
                                        element_info['highlighted_properties'][keyword].append({
                                            'property': prop_name,
                                            'value': prop_value,
                                            'pset': pset_name
                                        })
            except Exception as e:
                element_info['properties'] = {'error': str(e)}
            
            # Get spatial context
            if include_spatial_analysis:
                try:
                    container = ifcopenshell.util.element.get_container(element)
                    if container:
                        container_info = {
                            'id': container.id(),
                            'name': container.Name,
                            'type': container.is_a(),
                            'global_id': getattr(container, 'GlobalId', None)
                        }
                        element_info['spatial_context'] = container_info
                        
                        # Update spatial distribution
                        location_key = f"{container_info['name']} ({container_info['type']})"
                        if location_key not in result['spatial_distribution']:
                            result['spatial_distribution'][location_key] = {
                                'count': 0,
                                'elements': []
                            }
                        result['spatial_distribution'][location_key]['count'] += 1
                        result['spatial_distribution'][location_key]['elements'].append(element_info['id'])
                        
                        result['summary']['elements_with_spatial_context'] += 1
                except Exception as e:
                    element_info['spatial_context'] = {'error': str(e)}
            
            # Add to elements list if details are requested
            if include_details:
                result['elements'].append(element_info)
        
        # Perform property aggregation analysis
        for field in aggregation_fields:
            field_values = {}
            
            for element in result['elements']:
                value = None
                
                # Check basic attributes first
                if hasattr(element, field.lower()):
                    value = getattr(element, field.lower())
                elif field in element:
                    value = element[field]
                
                # Check in properties
                if value is None and element['properties']:
                    for pset_data in element['properties'].values():
                        if isinstance(pset_data, dict) and field in pset_data:
                            value = pset_data[field]
                            break
                
                if value is not None:
                    # Convert to string for grouping
                    value_key = str(value)
                    if value_key not in field_values:
                        field_values[value_key] = {'count': 0, 'elements': []}
                    field_values[value_key]['count'] += 1
                    field_values[value_key]['elements'].append(element['id'])
            
            if field_values:
                result['property_analysis'][field] = field_values
        
        return result
        
    except Exception as e:
        # Return error information
        result['error'] = str(e)
        return result