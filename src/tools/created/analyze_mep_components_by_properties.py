import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def analyze_mep_components_by_properties(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_mappings: Dict[str, Dict[str, Any]],
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Analyzes MEP components of a specified IFC element type by extracting specific properties 
    from known property sets, categorizing them by those properties, and tracking distribution 
    by building level.
    
    This function is designed for common MEP analysis tasks like 'what filter types are used 
    and where are they located?' or 'what pump types exist and their distribution by floor?'.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcFilter', 'IfcFlowTerminal', 'IfcDuctSegment')
        property_mappings: Dict mapping property categories to extraction rules, e.g.:
            {'type': {'property_set': 'Text', 'property_name': 'Filtertyp', 'fallback_fields': ['ObjectType', 'Name']},
             'level': {'property_set': 'Abhängigkeiten', 'property_name': 'Ebene', 'fallback_fields': []}}
        include_details: Boolean to include detailed element information (default: False)
    
    Returns:
        Dict containing:
        - 'summary': Dict with total counts and categories found
        - 'categories': Dict of category names with counts
        - 'distribution': Dict of categories by level with counts
        - 'elements': List of detailed element information (if include_details=True)
    
    Example:
        >>> import ifcopenshell
        >>> ifc_file = ifcopenshell.open('ventilation.ifc')
        >>> property_mappings = {
        ...     'type': {'property_set': 'Text', 'property_name': 'Filtertyp', 'fallback_fields': ['ObjectType', 'Name']},
        ...     'level': {'property_set': 'Abhängigkeiten', 'property_name': 'Ebene', 'fallback_fields': []}
        ... }
        >>> result = analyze_mep_components_by_properties(ifc_file, 'IfcFilter', property_mappings)
        >>> print(result['summary'])
    """
    try:
        # Initialize result structure
        result = {
            'summary': {
                'total_elements': 0,
                'categories_found': [],
                'levels_found': []
            },
            'categories': {},
            'distribution': {},
            'elements': []
        }
        
        # Get elements of specified type
        elements = list(ifc_file.by_type(element_type))
        result['summary']['total_elements'] = len(elements)
        
        if not elements:
            return result
        
        # Process each element
        for element in elements:
            try:
                # Get property sets
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Extract properties based on mappings
                extracted_values = {}
                element_details = {
                    'element_id': element.id(),
                    'element_name': element.Name,
                    'element_type': element.is_a(),
                    'properties': {}
                }
                
                for category, mapping in property_mappings.items():
                    value = None
                    
                    # Try to get from specified property set and property name
                    property_set = mapping.get('property_set')
                    property_name = mapping.get('property_name')
                    
                    if property_set and property_name:
                        if property_set in psets and property_name in psets[property_set]:
                            value = str(psets[property_set][property_name])
                    
                    # Fallback to specified fields if not found
                    if not value:
                        for field in mapping.get('fallback_fields', []):
                            if hasattr(element, field) and getattr(element, field):
                                value = str(getattr(element, field))
                                break
                    
                    extracted_values[category] = value
                    element_details['properties'][category] = value
                
                # Skip if primary category (usually 'type') not found
                primary_category = list(property_mappings.keys())[0]
                if not extracted_values.get(primary_category):
                    continue
                
                # Update categories count
                category_value = extracted_values[primary_category]
                if category_value not in result['categories']:
                    result['categories'][category_value] = 0
                result['categories'][category_value] += 1
                
                # Update distribution by level
                level_value = extracted_values.get('level')
                if level_value:
                    if category_value not in result['distribution']:
                        result['distribution'][category_value] = {}
                    if level_value not in result['distribution'][category_value]:
                        result['distribution'][category_value][level_value] = 0
                    result['distribution'][category_value][level_value] += 1
                
                # Add element details if requested
                if include_details:
                    result['elements'].append(element_details)
                
            except Exception as e:
                # Continue processing other elements if one fails
                continue
        
        # Update summary
        result['summary']['categories_found'] = list(result['categories'].keys())
        all_levels = set()
        for category_dist in result['distribution'].values():
            all_levels.update(category_dist.keys())
        result['summary']['levels_found'] = list(all_levels)
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'summary': {'total_elements': 0, 'categories_found': [], 'levels_found': []},
            'categories': {},
            'distribution': {},
            'elements': []
        }