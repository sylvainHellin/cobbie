import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.selector
from typing import List, Dict, Any, Optional, Union


def discover_domain_components_by_strategy(
    ifc_file: ifcopenshell.file,
    domain_keywords: List[str],
    domain_element_types: Optional[List[str]] = None,
    include_element_inventory: bool = True,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Discovers components of a specific domain (electrical, mechanical, plumbing, etc.) in an IFC model
    using a systematic multi-strategy approach.
    
    This function implements a comprehensive discovery workflow that:
    1) Checks what element types exist in the model
    2) Searches for domain-specific element types with schema compatibility handling
    3) Performs keyword-based searches across properties and names
    4) Provides categorized results with counts and details
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        domain_keywords: List of keywords related to the target domain
            (e.g., ['electric', 'electrical', 'lighting', 'switch'] for electrical)
        domain_element_types: Optional list of domain-specific IFC element types to check
            (e.g., ['IfcElectricAppliance', 'IfcLightFixture'] for electrical)
        include_element_inventory: Boolean to include element type inventory in results
        include_details: Boolean to include detailed element information
    
    Returns:
        Dict with discovery results including:
        - 'element_inventory': Dict of all element types and their counts
        - 'domain_element_types_found': Dict of domain-specific element types found
        - 'keyword_search_results': Dict of elements matching domain keywords
        - 'summary': Dict with total counts and statistics
        - 'elements_by_category': Dict categorizing found elements
    
    Example:
        >>> import ifcopenshell
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> electrical_keywords = ['electric', 'electrical', 'lighting', 'switch']
        >>> electrical_types = ['IfcElectricAppliance', 'IfcLightFixture']
        >>> results = discover_domain_components_by_strategy(
        ...     ifc_file, electrical_keywords, electrical_types
        ... )
        >>> print(f"Found {results['summary']['total_domain_elements']} electrical components")
    """
    
    # Initialize results structure
    results = {
        'element_inventory': {},
        'domain_element_types_found': {},
        'keyword_search_results': {
            'by_name': [],
            'by_properties': [],
            'by_object_type': []
        },
        'summary': {
            'total_elements': 0,
            'total_domain_elements': 0,
            'element_types_checked': 0,
            'strategies_used': []
        },
        'elements_by_category': {}
    }
    
    try:
        # Strategy 1: Element Type Inventory
        if include_element_inventory:
            element_types = {}
            for element in ifc_file:
                element_type = element.is_a()
                if element_type not in element_types:
                    element_types[element_type] = 0
                element_types[element_type] += 1
            
            results['element_inventory'] = element_types
            results['summary']['total_elements'] = sum(element_types.values())
            results['summary']['strategies_used'].append('element_inventory')
        
        # Strategy 2: Domain-Specific Element Type Search
        if domain_element_types:
            results['summary']['strategies_used'].append('domain_element_types')
            for elem_type in domain_element_types:
                try:
                    elements = ifc_file.by_type(elem_type)
                    if elements:
                        results['domain_element_types_found'][elem_type] = {
                            'count': len(elements),
                            'elements': []
                        }
                        
                        for elem in elements:
                            element_info = {
                                'id': elem.id(),
                                'Name': getattr(elem, 'Name', None),
                                'ObjectType': getattr(elem, 'ObjectType', None),
                                'Type': elem.is_a()
                            }
                            
                            if include_details:
                                # Get property sets for detailed information
                                try:
                                    psets = ifcopenshell.util.element.get_psets(elem)
                                    element_info['properties'] = psets
                                except:
                                    element_info['properties'] = {}
                            
                            results['domain_element_types_found'][elem_type]['elements'].append(element_info)
                    
                    results['summary']['element_types_checked'] += 1
                    
                except RuntimeError as e:
                    # Handle schema compatibility issues
                    if "not found in schema" in str(e):
                        results['domain_element_types_found'][elem_type] = {
                            'count': 0,
                            'error': f'Element type not supported in schema',
                            'elements': []
                        }
                    else:
                        results['domain_element_types_found'][elem_type] = {
                            'count': 0,
                            'error': str(e),
                            'elements': []
                        }
        
        # Strategy 3: Keyword-Based Search
        if domain_keywords:
            results['summary']['strategies_used'].append('keyword_search')
            
            # Search by element names
            for element in ifc_file:
                element_name = getattr(element, 'Name', '')
                if element_name and any(
                    keyword.lower() in str(element_name).lower() 
                    for keyword in domain_keywords
                ):
                    element_info = {
                        'id': element.id(),
                        'Name': element_name,
                        'Type': element.is_a(),
                        'ObjectType': getattr(element, 'ObjectType', None)
                    }
                    
                    if include_details:
                        try:
                            psets = ifcopenshell.util.element.get_psets(element)
                            element_info['properties'] = psets
                        except:
                            element_info['properties'] = {}
                    
                    results['keyword_search_results']['by_name'].append(element_info)
            
            # Search by object type
            for element in ifc_file:
                object_type = getattr(element, 'ObjectType', '')
                if object_type and any(
                    keyword.lower() in str(object_type).lower() 
                    for keyword in domain_keywords
                ):
                    element_info = {
                        'id': element.id(),
                        'Name': getattr(element, 'Name', None),
                        'Type': element.is_a(),
                        'ObjectType': object_type
                    }
                    
                    if include_details:
                        try:
                            psets = ifcopenshell.util.element.get_psets(element)
                            element_info['properties'] = psets
                        except:
                            element_info['properties'] = {}
                    
                    results['keyword_search_results']['by_object_type'].append(element_info)
            
            # Search by property values
            for element in ifc_file:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    matching_properties = {}
                    
                    for pset_name, pset_data in psets.items():
                        for prop_name, prop_value in pset_data.items():
                            if any(
                                keyword.lower() in str(prop_value).lower() 
                                for keyword in domain_keywords
                            ):
                                if pset_name not in matching_properties:
                                    matching_properties[pset_name] = {}
                                matching_properties[pset_name][prop_name] = prop_value
                    
                    if matching_properties:
                        element_info = {
                            'id': element.id(),
                            'Name': getattr(element, 'Name', None),
                            'Type': element.is_a(),
                            'ObjectType': getattr(element, 'ObjectType', None),
                            'matching_properties': matching_properties
                        }
                        
                        if include_details:
                            element_info['properties'] = psets
                        
                        results['keyword_search_results']['by_properties'].append(element_info)
                        
                except:
                    continue  # Skip elements that can't be processed
        
        # Calculate summary statistics
        total_domain_elements = 0
        
        # Count from domain element types
        for elem_type_data in results['domain_element_types_found'].values():
            total_domain_elements += elem_type_data.get('count', 0)
        
        # Count from keyword searches (avoiding duplicates)
        all_keyword_elements = set()
        for category in ['by_name', 'by_properties', 'by_object_type']:
            for element in results['keyword_search_results'][category]:
                all_keyword_elements.add(element['id'])
        
        total_domain_elements += len(all_keyword_elements)
        
        results['summary']['total_domain_elements'] = total_domain_elements
        
        # Categorize elements
        results['elements_by_category'] = {
            'domain_specific_types': results['domain_element_types_found'],
            'keyword_matches': {
                'by_name': results['keyword_search_results']['by_name'],
                'by_properties': results['keyword_search_results']['by_properties'],
                'by_object_type': results['keyword_search_results']['by_object_type']
            }
        }
        
    except Exception as e:
        results['error'] = str(e)
    
    return results