import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def search_properties_by_keywords_multilingual(
    ifc_file,
    element_type: str,
    property_keywords: List[str],
    max_elements_to_analyze: int = 50,
    include_property_values: bool = True,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Searches for technical properties in IFC elements using multilingual keyword filtering across all property sets.
    
    This function systematically examines property sets for elements of a specified type, looking for 
    properties that contain domain-specific keywords in multiple languages. It's particularly useful for 
    finding technical specifications like fire ratings, acoustic properties, or thermal performance data 
    when property names might be in different languages or stored in non-standard property sets.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcDoor', 'IfcWall')
        property_keywords: List of keywords to search for, can include multiple languages
        max_elements_to_analyze: Limit for performance, default 50
        include_property_values: Whether to extract actual values, default True
        case_sensitive: Keyword matching sensitivity, default False
    
    Returns:
        Dict containing:
        - found_properties: List of property_set.property_name combinations
        - property_details: Detailed information about each found property including element info and values
        - summary_statistics: Counts and distribution of findings
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = search_properties_by_keywords_multilingual(
        ...     model, 
        ...     'IfcDoor', 
        ...     ['fire', 'brand', 'feuer', 'rating', 'klasse']
        ... )
        >>> print(result['found_properties'])
        ['ID-Daten.Feuerwiderstandsklasse']
    """
    try:
        # Initialize result structure
        result = {
            'found_properties': [],
            'property_details': [],
            'summary_statistics': {
                'total_elements_analyzed': 0,
                'elements_with_matching_properties': 0,
                'unique_property_sets': set(),
                'unique_property_names': set(),
                'total_matches': 0
            }
        }
        
        # Get elements of specified type
        elements = ifc_file.by_type(element_type)
        
        if not elements:
            return result
            
        # Limit elements for performance
        elements_to_analyze = elements[:max_elements_to_analyze]
        result['summary_statistics']['total_elements_analyzed'] = len(elements_to_analyze)
        
        # Prepare keywords for matching
        if not case_sensitive:
            search_keywords = [keyword.lower() for keyword in property_keywords]
        else:
            search_keywords = property_keywords
        
        elements_with_matches = set()
        
        # Iterate through elements and search for matching properties
        for element in elements_to_analyze:
            try:
                # Get all property sets for the element
                psets = ifcopenshell.util.element.get_psets(element)
                
                element_has_match = False
                
                # Search through each property set
                for pset_name, properties in psets.items():
                    for prop_name, prop_value in properties.items():
                        # Check if property name contains any of the keywords
                        search_text = prop_name if case_sensitive else prop_name.lower()
                        
                        if any(keyword in search_text for keyword in search_keywords):
                            # Found a matching property
                            property_key = f"{pset_name}.{prop_name}"
                            
                            # Add to found properties if not already there
                            if property_key not in result['found_properties']:
                                result['found_properties'].append(property_key)
                            
                            # Update statistics
                            result['summary_statistics']['unique_property_sets'].add(pset_name)
                            result['summary_statistics']['unique_property_names'].add(prop_name)
                            result['summary_statistics']['total_matches'] += 1
                            element_has_match = True
                            
                            # Create detailed property information
                            property_detail = {
                                'element_id': element.id(),
                                'element_name': getattr(element, 'Name', None) or 'Unnamed',
                                'element_type': element_type,
                                'property_set': pset_name,
                                'property_name': prop_name,
                                'property_value': prop_value if include_property_values else None,
                                'matched_keywords': [kw for kw in search_keywords if kw in search_text]
                            }
                            
                            result['property_details'].append(property_detail)
                
                if element_has_match:
                    elements_with_matches.add(element.id())
                    
            except Exception as e:
                # Continue processing other elements if one fails
                continue
        
        # Finalize statistics
        result['summary_statistics']['elements_with_matching_properties'] = len(elements_with_matches)
        result['summary_statistics']['unique_property_sets'] = list(result['summary_statistics']['unique_property_sets'])
        result['summary_statistics']['unique_property_names'] = list(result['summary_statistics']['unique_property_names'])
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'found_properties': [],
            'property_details': [],
            'summary_statistics': {'error': str(e)},
            'error': True
        }