import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def categorize_elements_by_semantic_keywords(
    ifc_file: ifcopenshell.file,
    element_type: str,
    categorization_rules: Dict[str, List[str]],
    search_fields: List[str] = ['Name', 'ObjectType'],
    include_properties: bool = True,
    case_sensitive: bool = False,
    include_summary: bool = True
) -> Dict[str, Any]:
    """
    Categorizes IFC elements of a specified type into semantic groups based on keyword matching.
    
    This function handles the common BIM analysis pattern where elements of the same IFC type
    need to be separated by their functional meaning (e.g., separating sanitary fixtures from 
    lighting equipment in IfcFlowTerminal, or categorizing doors by their function).
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcFlowTerminal', 'IfcDoor')
        categorization_rules: Dict mapping category names to lists of keywords
            (e.g., {'Sanitary': ['toilet', 'sink', 'urinal'], 'Lighting': ['light', 'luminaire']})
        search_fields: List of element fields to search for keywords (default: ['Name', 'ObjectType'])
        include_properties: Boolean to include property sets in results (default: True)
        case_sensitive: Boolean for case-sensitive keyword matching (default: False)
        include_summary: Boolean to include summary statistics (default: True)
    
    Returns:
        Dict containing:
        - 'categories': Dict mapping category names to lists of matching elements
        - 'uncategorized': List of elements that didn't match any category
        - 'summary': Dict with counts and percentages for each category
        - 'total_elements': Total number of elements analyzed
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> rules = {
        ...     'Sanitary': ['toilet', 'sink', 'urinal', 'wash'],
        ...     'Lighting': ['light', 'luminaire', 'lamp']
        ... }
        >>> result = categorize_elements_by_semantic_keywords(
        ...     ifc_file, 'IfcFlowTerminal', rules
        ... )
        >>> print(f"Found {result['summary']['Sanitary']['count']} sanitary fixtures")
    """
    
    try:
        # Initialize result structure
        result = {
            'categories': {category: [] for category in categorization_rules.keys()},
            'uncategorized': [],
            'summary': {},
            'total_elements': 0
        }
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        result['total_elements'] = len(elements)
        
        if not elements:
            return result
        
        # Process each element
        for element in elements:
            element_info = {
                'GlobalId': getattr(element, 'GlobalId', ''),
                'Name': getattr(element, 'Name', ''),
                'ObjectType': getattr(element, 'ObjectType', ''),
                'PredefinedType': getattr(element, 'PredefinedType', 'N/A')
            }
            
            # Include property sets if requested
            if include_properties:
                try:
                    element_info['property_sets'] = ifcopenshell.util.element.get_psets(element)
                except:
                    element_info['property_sets'] = {}
            
            # Determine category by searching for keywords
            matched_category = None
            
            for category, keywords in categorization_rules.items():
                # Search in specified fields
                for field in search_fields:
                    field_value = getattr(element, field, '')
                    if field_value:
                        # Check each keyword for this category
                        for keyword in keywords:
                            if case_sensitive:
                                if keyword in str(field_value):
                                    matched_category = category
                                    break
                            else:
                                if keyword.lower() in str(field_value).lower():
                                    matched_category = category
                                    break
                        
                        if matched_category:
                            break
                
                if matched_category:
                    break
            
            # Also search in property sets if included
            if not matched_category and include_properties and 'property_sets' in element_info:
                for pset_name, pset_properties in element_info['property_sets'].items():
                    if isinstance(pset_properties, dict):
                        for prop_name, prop_value in pset_properties.items():
                            combined_text = f"{prop_name} {prop_value}"
                            for category, keywords in categorization_rules.items():
                                for keyword in keywords:
                                    if case_sensitive:
                                        if keyword in str(combined_text):
                                            matched_category = category
                                            break
                                    else:
                                        if keyword.lower() in str(combined_text).lower():
                                            matched_category = category
                                            break
                                if matched_category:
                                    break
                            if matched_category:
                                break
                        if matched_category:
                            break
                    if matched_category:
                        break
            
            # Add element to appropriate category
            if matched_category and matched_category in result['categories']:
                result['categories'][matched_category].append(element_info)
            else:
                result['uncategorized'].append(element_info)
        
        # Generate summary if requested
        if include_summary:
            total_categorized = sum(len(elements) for elements in result['categories'].values())
            total_with_uncategorized = total_categorized + len(result['uncategorized'])
            
            for category, elements in result['categories'].items():
                count = len(elements)
                percentage = (count / total_with_uncategorized * 100) if total_with_uncategorized > 0 else 0
                result['summary'][category] = {
                    'count': count,
                    'percentage': round(percentage, 1)
                }
            
            # Add uncategorized to summary
            uncategorized_count = len(result['uncategorized'])
            uncategorized_percentage = (uncategorized_count / total_with_uncategorized * 100) if total_with_uncategorized > 0 else 0
            result['summary']['Uncategorized'] = {
                'count': uncategorized_count,
                'percentage': round(uncategorized_percentage, 1)
            }
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'categories': {},
            'uncategorized': [],
            'summary': {},
            'total_elements': 0
        }