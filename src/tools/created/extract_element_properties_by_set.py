import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional

def extract_element_properties_by_set(
    ifc_file,
    element_type: str,
    property_set_mapping: Dict[str, List[str]],
    check_placeholders: bool = True,
    placeholder_patterns: Optional[List[str]] = None,
    include_element_details: bool = True
) -> Dict[str, Any]:
    """
    Extracts specific properties from designated property sets for IFC elements of a given type,
    with optional data quality assessment.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcWindow', 'IfcDoor')
        property_set_mapping: Dict mapping property set names to lists of property names to extract
            (e.g., {'PSet_Revit_Type_Other': ['WarrantyDurationLabor', 'WarrantyDurationParts']})
        check_placeholders: Boolean to identify placeholder text vs real data (default: True)
        placeholder_patterns: List of patterns to identify placeholder values
            (default: uses property names as common placeholders)
        include_element_details: Boolean to include basic element info (default: True)
    
    Returns:
        Dict containing:
        - elements: List of dicts with element info and extracted property values
        - summary: Dict with counts of elements with real vs placeholder data
        - property_coverage: Dict showing which properties were found and their value types
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = extract_element_properties_by_set(
        ...     model,
        ...     'IfcWindow',
        ...     {'PSet_Revit_Type_Other': ['WarrantyDurationLabor', 'WarrantyDurationParts']}
        ... )
        >>> print(result['summary'])
    """
    try:
        # Initialize result structure
        result = {
            'elements': [],
            'summary': {
                'total_elements': 0,
                'elements_with_real_data': 0,
                'elements_with_placeholder_data': 0,
                'elements_with_missing_data': 0
            },
            'property_coverage': {}
        }
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        result['summary']['total_elements'] = len(elements)
        
        if not elements:
            return result
        
        # Initialize property coverage tracking
        for pset_name, prop_names in property_set_mapping.items():
            for prop_name in prop_names:
                key = f"{pset_name}.{prop_name}"
                result['property_coverage'][key] = {
                    'found_count': 0,
                    'real_data_count': 0,
                    'placeholder_count': 0,
                    'value_types': set()
                }
        
        # Generate default placeholder patterns if not provided
        if placeholder_patterns is None:
            placeholder_patterns = []
            for pset_name, prop_names in property_set_mapping.items():
                for prop_name in prop_names:
                    placeholder_patterns.append(prop_name)  # Property name as placeholder
                    placeholder_patterns.append(f"{prop_name}")  # Property name with quotes
        
        # Process each element
        for element in elements:
            element_data = {}
            
            if include_element_details:
                element_data.update({
                    'id': element.id(),
                    'name': element.Name or '',
                    'global_id': element.GlobalId or ''
                })
            
            # Get all property sets for the element
            psets = ifcopenshell.util.element.get_psets(element)
            
            element_has_real_data = False
            element_has_placeholder_data = False
            
            # Extract requested properties
            for pset_name, prop_names in property_set_mapping.items():
                if pset_name in psets:
                    pset_data = psets[pset_name]
                    for prop_name in prop_names:
                        if prop_name in pset_data:
                            prop_value = pset_data[prop_name]
                            prop_key = f"{pset_name}.{prop_name}"
                            
                            # Store the value
                            element_data[prop_key] = prop_value
                            
                            # Update coverage
                            result['property_coverage'][prop_key]['found_count'] += 1
                            result['property_coverage'][prop_key]['value_types'].add(type(prop_value).__name__)
                            
                            # Check for placeholder data
                            is_placeholder = False
                            if check_placeholders and prop_value is not None:
                                prop_str = str(prop_value).strip()
                                for pattern in placeholder_patterns:
                                    if pattern.lower() in prop_str.lower():
                                        is_placeholder = True
                                        break
                                
                                # Additional check: if value equals property name (common placeholder pattern)
                                if prop_str.lower() == prop_name.lower():
                                    is_placeholder = True
                            
                            if is_placeholder:
                                element_has_placeholder_data = True
                                result['property_coverage'][prop_key]['placeholder_count'] += 1
                            elif prop_value is not None and prop_value != '':
                                element_has_real_data = True
                                result['property_coverage'][prop_key]['real_data_count'] += 1
            
            # Update element summary
            if element_has_real_data:
                result['summary']['elements_with_real_data'] += 1
            elif element_has_placeholder_data:
                result['summary']['elements_with_placeholder_data'] += 1
            else:
                result['summary']['elements_with_missing_data'] += 1
            
            result['elements'].append(element_data)
        
        # Convert sets to lists for JSON serialization
        for prop_key in result['property_coverage']:
            result['property_coverage'][prop_key]['value_types'] = list(
                result['property_coverage'][prop_key]['value_types']
            )
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'elements': [],
            'summary': {},
            'property_coverage': {}
        }