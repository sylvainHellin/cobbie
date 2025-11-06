import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Tuple, Any, Optional

def filter_elements_by_keywords(
    ifc_file,
    element_type: str,
    include_keywords: List[str],
    exclude_keywords: Optional[List[str]] = None,
    category_field: str = 'ObjectType',
    include_properties: bool = True
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Filters and categorizes IFC elements based on semantic keywords in their properties.
    
    This function is useful when elements of the same IFC type need to be separated by their
    functional meaning (e.g., separating sanitary fixtures from lighting equipment in IfcFlowTerminal,
    or fire-rated doors from regular doors in IfcDoor).
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcFlowTerminal', 'IfcDoor')
        include_keywords: List of keywords to include (case-insensitive)
        exclude_keywords: List of keywords to exclude (case-insensitive), defaults to None
        category_field: Field to use for categorization, defaults to 'ObjectType'
        include_properties: Whether to extract property sets, defaults to True
    
    Returns:
        Tuple of (categories_dict, summary_dict) where:
        - categories_dict maps category names to lists of element dictionaries with properties
        - summary_dict contains total counts and metadata
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> categories, summary = filter_elements_by_keywords(
        ...     model, 'IfcFlowTerminal',
        ...     include_keywords=['toilet', 'sink', 'urinal'],
        ...     exclude_keywords=['lighting']
        ... )
        >>> print(f"Found {summary['total_elements']} elements in {summary['total_categories']} categories")
    """
    
    # Initialize return structures
    categories: Dict[str, List[Dict[str, Any]]] = {}
    summary: Dict[str, Any] = {
        'element_type': element_type,
        'include_keywords': include_keywords,
        'exclude_keywords': exclude_keywords or [],
        'category_field': category_field,
        'total_elements': 0,
        'total_categories': 0,
        'filtered_by_keywords': True
    }
    
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Filter elements based on keywords
        filtered_elements = []
        exclude_keywords = exclude_keywords or []
        
        for element in elements:
            # Get text content from relevant fields for keyword matching
            name = element.Name or ''
            object_type = element.ObjectType or ''
            long_name = getattr(element, 'LongName', '') or ''
            
            # Combine all text fields for searching
            search_text = (name + ' ' + object_type + ' ' + long_name).lower()
            
            # Check include keywords
            has_include_keyword = any(keyword.lower() in search_text for keyword in include_keywords)
            
            # Check exclude keywords
            has_exclude_keyword = any(keyword.lower() in search_text for keyword in exclude_keywords)
            
            # Apply filtering logic
            if has_include_keyword and not has_exclude_keyword:
                filtered_elements.append(element)
        
        # Categorize filtered elements
        for element in filtered_elements:
            # Get category value from specified field
            category_value = getattr(element, category_field, None)
            if category_value is None:
                # Fallback to Name if category_field is not available
                category_value = element.Name or 'Unknown'
            
            category = str(category_value)
            
            # Initialize category if not exists
            if category not in categories:
                categories[category] = []
            
            # Create element info dictionary
            element_info: Dict[str, Any] = {
                'GlobalId': element.GlobalId,
                'Name': element.Name,
                'ObjectType': element.ObjectType,
                'LongName': getattr(element, 'LongName', None)
            }
            
            # Add property sets if requested
            if include_properties:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    element_info['PropertySets'] = psets
                except Exception as e:
                    element_info['PropertySets'] = {}
                    element_info['PropertySetsError'] = str(e)
            
            categories[category].append(element_info)
        
        # Update summary
        summary['total_elements'] = len(filtered_elements)
        summary['total_categories'] = len(categories)
        
        return categories, summary
        
    except Exception as e:
        # Handle errors gracefully
        summary['error'] = str(e)
        summary['total_elements'] = 0
        summary['total_categories'] = 0
        return {}, summary