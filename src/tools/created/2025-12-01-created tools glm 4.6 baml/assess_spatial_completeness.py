import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def assess_spatial_completeness(
    ifc_file: ifcopenshell.file,
    spatial_element_types: List[str] = ['IfcSpace', 'IfcZone', 'IfcBuildingStorey'],
    building_categorization_keywords: Dict[str, List[str]] = {'residential': ['haus', 'wohn', 'apartment', 'residential']},
    include_building_analysis: bool = True,
    max_buildings_to_analyze: int = 5
) -> Dict[str, Any]:
    """
    Assesses whether an IFC model contains interior spatial information and provides a diagnostic summary.
    
    This function answers the fundamental question 'does this model have interior layout data?' by checking
    for spatial elements and analyzing building content. It's particularly useful for quickly determining if
    detailed interior analysis is possible or if the model is limited to exterior/structural representation.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        spatial_element_types: List of spatial element types to check for
        building_categorization_keywords: Dict for categorizing buildings by keywords in their names
        include_building_analysis: Boolean to include detailed building content analysis
        max_buildings_to_analyze: Maximum buildings to examine in detail
    
    Returns:
        Dict containing:
        - spatial_elements_found: Dict of spatial element types and their counts
        - has_spatial_data: Boolean indicating if any spatial elements exist
        - building_summary: Total buildings and categorization
        - building_content_analysis: Sample buildings with their contained element types
        - assessment: Summary of what type of model this appears to be
        - recommendations: What analysis is possible given the available data
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = assess_spatial_completeness(model)
        >>> print(result['has_spatial_data'])
        False
    """
    
    result = {
        'spatial_elements_found': {},
        'has_spatial_data': False,
        'building_summary': {},
        'building_content_analysis': [],
        'assessment': '',
        'recommendations': []
    }
    
    try:
        # Check for spatial elements
        total_spatial_elements = 0
        for spatial_type in spatial_element_types:
            try:
                elements = list(ifc_file.by_type(spatial_type))
                count = len(elements)
                result['spatial_elements_found'][spatial_type] = count
                total_spatial_elements += count
            except RuntimeError:
                # Element type not available in schema
                result['spatial_elements_found'][spatial_type] = 0
        
        result['has_spatial_data'] = total_spatial_elements > 0
        
        # Analyze buildings
        buildings = list(ifc_file.by_type('IfcBuilding'))
        result['building_summary']['total_buildings'] = len(buildings)
        result['building_summary']['categorized_buildings'] = {}
        
        # Categorize buildings
        for category, keywords in building_categorization_keywords.items():
            categorized_count = 0
            for building in buildings:
                building_name = (building.Name or '').lower()
                building_longname = (building.LongName or '').lower()
                
                for keyword in keywords:
                    if keyword in building_name or keyword in building_longname:
                        categorized_count += 1
                        break
            result['building_summary']['categorized_buildings'][category] = categorized_count
        
        # Analyze building content if requested
        if include_building_analysis and buildings:
            buildings_to_analyze = buildings[:max_buildings_to_analyze]
            
            for building in buildings_to_analyze:
                building_info = {
                    'name': building.Name,
                    'long_name': building.LongName,
                    'contained_elements': {},
                    'total_elements': 0
                }
                
                # Get contained elements
                contained_elements = []
                for rel in building.ContainsElements:
                    if rel.is_a('IfcRelContainedInSpatialStructure'):
                        contained_elements.extend(rel.RelatedElements)
                
                building_info['total_elements'] = len(contained_elements)
                
                # Count element types
                for element in contained_elements:
                    elem_type = element.is_a()
                    building_info['contained_elements'][elem_type] = building_info['contained_elements'].get(elem_type, 0) + 1
                
                result['building_content_analysis'].append(building_info)
        
        # Generate assessment
        if result['has_spatial_data']:
            result['assessment'] = 'Architectural model with interior spatial data'
            result['recommendations'] = [
                'Detailed interior layout analysis is possible',
                'Space-based analysis and room relationships can be performed',
                'Building storey hierarchy is available for vertical analysis'
            ]
        else:
            if result['building_summary']['total_buildings'] > 50:
                result['assessment'] = 'City-scale or urban planning model'
                result['recommendations'] = [
                    'Analysis limited to building exterior and urban context',
                    'No interior layout data available',
                    'Focus on building relationships and urban analysis'
                ]
            else:
                result['assessment'] = 'Architectural model with exterior/structural elements only'
                result['recommendations'] = [
                    'Analysis limited to building envelope and structural elements',
                    'No room or space definitions available',
                    'Consider wall and door analysis for basic layout inference'
                ]
        
    except Exception as e:
        result['error'] = str(e)
        result['assessment'] = 'Error during analysis'
        result['recommendations'] = ['Check model integrity and try again']
    
    return result