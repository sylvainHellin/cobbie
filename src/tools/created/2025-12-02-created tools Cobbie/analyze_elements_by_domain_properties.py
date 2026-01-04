import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def analyze_elements_by_domain_properties(
    ifc_file: ifcopenshell.file,
    element_type: str,
    domain_keywords: List[str],
    group_by_field: str = 'ObjectType',
    case_sensitive: bool = False,
    max_elements: int = 1000,
    include_examples: int = 2,
    property_sets_filter: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyzes IFC elements to find those containing domain-specific properties, with flexible keyword matching and type-based grouping.
    
    This function handles the common BIM analysis task of discovering elements that have properties related to a specific domain
    (e.g., fire safety, acoustics, thermal performance) when the exact property names and locations may vary across models.
    It provides comprehensive results including element counts, property details, and examples grouped by element type.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcDoor', 'IfcWall', 'IfcWindow')
        domain_keywords: List of keywords related to the domain (e.g., ['fire', 'rating', 'resistance', 'protection'])
        group_by_field: Field to group results by ('ObjectType', 'Name', 'Description') - default 'ObjectType'
        case_sensitive: Whether keyword matching should be case sensitive - default False
        max_elements: Maximum number of elements to analyze - default 1000
        include_examples: Number of example elements to include per group - default 2
        property_sets_filter: Optional list of property set names to prioritize - default None
    
    Returns:
        Dict containing:
        - total_elements: Total elements analyzed
        - elements_with_domain_properties: Count of elements containing domain properties
        - type_groups: Dictionary grouping results by element type with counts, property details, and examples
        - all_matches: List of all individual matches with full details
        - summary: Brief summary of findings
    
    Example usage:
        ```python
        import ifcopenshell
        
        model = ifcopenshell.open('building.ifc')
        result = analyze_elements_by_domain_properties(
            ifc_file=model,
            element_type='IfcDoor',
            domain_keywords=['fire', 'rating', 'resistance', 'protection'],
            group_by_field='ObjectType'
        )
        print(f"Found {result['elements_with_domain_properties']} doors with fire properties")
        ```
    """
    try:
        # Initialize result structure
        result = {
            'total_elements': 0,
            'elements_with_domain_properties': 0,
            'type_groups': {},
            'all_matches': [],
            'summary': ''
        }
        
        # Get elements of specified type
        elements = ifc_file.by_type(element_type)
        
        # Limit elements if specified
        if max_elements > 0 and len(elements) > max_elements:
            elements = elements[:max_elements]
        
        result['total_elements'] = len(elements)
        
        if not elements:
            result['summary'] = f"No {element_type} elements found in the model."
            return result
        
        # Prepare keywords for matching
        if not case_sensitive:
            domain_keywords = [kw.lower() for kw in domain_keywords]
        
        # Process each element
        for element in elements:
            try:
                # Get grouping field value
                group_value = getattr(element, group_by_field, None)
                if group_value is None:
                    group_value = 'Unknown'
                
                # Get element basic info
                element_info = {
                    'element_id': element.id(),
                    'name': getattr(element, 'Name', None) or 'N/A',
                    'group_value': group_value,
                    'matches': []
                }
                
                # Get property sets
                property_sets = ifcopenshell.util.element.get_psets(element)
                
                # Check for domain-related properties
                has_domain_property = False
                
                for pset_name, pset_properties in property_sets.items():
                    # Apply property set filter if specified
                    if property_sets_filter and pset_name not in property_sets_filter:
                        continue
                    
                    for prop_name, prop_value in pset_properties.items():
                        # Skip 'id' properties as they are internal
                        if prop_name.lower() == 'id':
                            continue
                        
                        # Check if property name matches domain keywords
                        prop_name_check = prop_name if case_sensitive else prop_name.lower()
                        
                        if any(keyword in prop_name_check for keyword in domain_keywords):
                            has_domain_property = True
                            match_info = {
                                'property_set': pset_name,
                                'property_name': prop_name,
                                'property_value': prop_value
                            }
                            element_info['matches'].append(match_info)
                
                # If element has domain properties, add to results
                if has_domain_property:
                    result['elements_with_domain_properties'] += 1
                    result['all_matches'].append(element_info)
                    
                    # Group by type
                    if group_value not in result['type_groups']:
                        result['type_groups'][group_value] = {
                            'count': 0,
                            'properties_found': {},
                            'examples': []
                        }
                    
                    result['type_groups'][group_value]['count'] += 1
                    
                    # Collect unique properties for this type
                    for match in element_info['matches']:
                        prop_key = f"{match['property_set']}.{match['property_name']}"
                        if prop_key not in result['type_groups'][group_value]['properties_found']:
                            result['type_groups'][group_value]['properties_found'][prop_key] = []
                        
                        # Add unique values
                        if match['property_value'] not in result['type_groups'][group_value]['properties_found'][prop_key]:
                            result['type_groups'][group_value]['properties_found'][prop_key].append(match['property_value'])
                    
                    # Add examples (limit as specified)
                    if len(result['type_groups'][group_value]['examples']) < include_examples:
                        result['type_groups'][group_value]['examples'].append({
                            'element_id': element_info['element_id'],
                            'name': element_info['name'],
                            'matches': element_info['matches']
                        })
            
            except Exception as e:
                # Continue processing other elements if one fails
                continue
        
        # Generate summary
        if result['elements_with_domain_properties'] == 0:
            result['summary'] = f"No {element_type} elements with domain properties found. Analyzed {result['total_elements']} elements."
        else:
            type_count = len(result['type_groups'])
            result['summary'] = f"Found {result['elements_with_domain_properties']} {element_type} elements with domain properties across {type_count} type(s) out of {result['total_elements']} total elements."
        
        return result
    
    except Exception as e:
        # Return error information
        return {
            'total_elements': 0,
            'elements_with_domain_properties': 0,
            'type_groups': {},
            'all_matches': [],
            'summary': f"Error analyzing elements: {str(e)}",
            'error': str(e)
        }