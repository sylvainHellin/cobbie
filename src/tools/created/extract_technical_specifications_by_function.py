import ifcopenshell
import ifcopenshell.util.selector
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union
import re

def extract_technical_specifications_by_function(
    ifc_file: ifcopenshell.file,
    element_type: str,
    functional_keywords: List[str],
    technical_keywords: List[str],
    search_fields: Optional[List[str]] = None,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Extracts technical specifications from IFC elements identified by their functional type using semantic keywords.
    
    This function combines element discovery by function with technical specification extraction,
    answering questions like 'what are the fire ratings of doors?' or 'what are the voltage ratings of outlets?'.
    It searches for elements using functional keywords, then extracts technical specifications from
    properties, names, or other metadata.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file object)
        element_type: IFC element type to search (e.g., 'IfcFlowTerminal', 'IfcDoor')
        functional_keywords: List of keywords to identify target function (e.g., ['toilet', 'wc', 'water closet'])
        technical_keywords: List of keywords to identify technical specs (e.g., ['water', 'efficiency', 'flow'])
        search_fields: Fields to search for technical data (default: ['Name', 'properties'])
        include_details: Whether to include element details in results (default: True)
    
    Returns:
        Dict containing:
        - 'found_elements': List of elements matching functional criteria
        - 'technical_specifications': Dict mapping element names to their technical specs
        - 'categories': Dict of categorized results by technical specification
        - 'summary': Dict with counts and statistics
        - 'errors': List of any errors encountered
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = extract_technical_specifications_by_function(
        ...     model,
        ...     'IfcFlowTerminal',
        ...     ['toilet', 'wc', 'water closet'],
        ...     ['water', 'efficiency', 'flow', 'flush'],
        ...     ['Name', 'properties']
        ... )
        >>> print(result['summary']['total_elements'])
        4
    """
    
    # Initialize result structure
    result = {
        'found_elements': [],
        'technical_specifications': {},
        'categories': {},
        'summary': {
            'total_elements': 0,
            'elements_with_specs': 0,
            'unique_specifications': set()
        },
        'errors': []
    }
    
    # Set default search fields if not provided
    if search_fields is None:
        search_fields = ['Name', 'properties']
    
    try:
        # Step 1: Filter elements by type
        elements = ifcopenshell.util.selector.filter_elements(ifc_file, element_type)
        result['summary']['total_elements'] = len(elements)
        
        # Step 2: Filter elements by functional keywords
        matching_elements = []
        for element in elements:
            element_matches = False
            element_info = {
                'id': element.id(),
                'type': element.is_a(),
                'name': getattr(element, 'Name', None),
                'properties': {},
                'technical_specs': {}
            }
            
            # Check functional keywords in name
            if element_info['name']:
                name_lower = str(element_info['name']).lower()
                if any(keyword.lower() in name_lower for keyword in functional_keywords):
                    element_matches = True
            
            # Check functional keywords in properties
            if not element_matches:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    element_info['properties'] = psets
                    
                    for pset_name, pset_data in psets.items():
                        if isinstance(pset_data, dict):
                            for prop_name, prop_value in pset_data.items():
                                prop_str = str(prop_value).lower()
                                if any(keyword.lower() in prop_str for keyword in functional_keywords):
                                    element_matches = True
                                    break
                        if element_matches:
                            break
                except Exception as e:
                    result['errors'].append(f"Error getting properties for element {element.id()}: {str(e)}")
            
            if element_matches:
                matching_elements.append(element_info)
        
        result['found_elements'] = matching_elements
        
        # Step 3: Extract technical specifications
        for element_info in matching_elements:
            element_id = element_info['id']
            element_name = element_info['name'] or f"Element_{element_id}"
            technical_specs = {}
            
            # Search in specified fields
            for field in search_fields:
                if field == 'Name' and element_info['name']:
                    # Search for technical keywords in name
                    name_str = str(element_info['name'])
                    for tech_keyword in technical_keywords:
                        if tech_keyword.lower() in name_str.lower():
                            # Try to extract numerical values and units
                            pattern = r'(\d+(?:\.\d+)?)\s*([a-zA-Z/]+)'
                            matches = re.findall(pattern, name_str)
                            if matches:
                                for value, unit in matches:
                                    spec_key = f"{tech_keyword}_value"
                                    technical_specs[spec_key] = f"{value} {unit}"
                                    technical_specs[f"{tech_keyword}_unit"] = unit
                                    technical_specs[f"{tech_keyword}_numeric"] = float(value)
                            else:
                                # If no numeric pattern found, store the whole match
                                technical_specs[tech_keyword] = name_str
                
                elif field == 'properties' and element_info['properties']:
                    # Search for technical keywords in properties
                    for pset_name, pset_data in element_info['properties'].items():
                        if isinstance(pset_data, dict):
                            for prop_name, prop_value in pset_data.items():
                                prop_str = str(prop_value).lower()
                                for tech_keyword in technical_keywords:
                                    if tech_keyword.lower() in prop_str or tech_keyword.lower() in prop_name.lower():
                                        technical_specs[f"{pset_name}.{prop_name}"] = prop_value
            
            element_info['technical_specs'] = technical_specs
            
            if technical_specs:
                result['technical_specifications'][element_name] = technical_specs
                result['summary']['elements_with_specs'] += 1
                
                # Categorize by primary technical specification (use first string value as category)
                for spec_key, spec_value in technical_specs.items():
                    if isinstance(spec_value, str) and not spec_key.endswith('_unit') and not spec_key.endswith('_numeric'):
                        # Create category based on the specification value
                        category = spec_value
                        if category not in result['categories']:
                            result['categories'][category] = []
                        if element_name not in result['categories'][category]:
                            result['categories'][category].append(element_name)
                        result['summary']['unique_specifications'].add(category)
                        break  # Only use first specification for categorization
        
        # Convert set to list for JSON serialization
        result['summary']['unique_specifications'] = list(result['summary']['unique_specifications'])
        
        # Remove detailed element info if not requested
        if not include_details:
            for element_info in result['found_elements']:
                element_info.pop('properties', None)
    
    except Exception as e:
        result['errors'].append(f"General error in extract_technical_specifications_by_function: {str(e)}")
    
    return result