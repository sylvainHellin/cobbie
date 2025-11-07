import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def filter_elements_by_property_and_keywords(
    ifc_file,
    element_type: str,
    property_filter: Dict[str, str],
    keywords: List[str],
    search_fields: List[str] = ['Name', 'LongName', 'ObjectType'],
    case_sensitive: bool = False,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Filters IFC elements by property values and then further filters the results by semantic keywords.
    
    This function combines property-based filtering with semantic keyword filtering to answer
    questions like 'find toilet rooms on the second floor' or 'get fire-rated doors on level 1'.
    It handles the common pattern where you first need to filter elements by their location/
    system/other properties stored in property sets, then identify specific functional types by
    their names or descriptions.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSpace', 'IfcDoor')
        property_filter: Dict with 'property_set', 'property_name', 'property_value' for initial filtering
        keywords: List of keywords to identify target elements (e.g., ['toilet', 'wc', 'restroom'])
        search_fields: List of fields to search for keywords (default: ['Name', 'LongName', 'ObjectType'])
        case_sensitive: Whether keyword matching should be case sensitive (default: False)
        include_details: Whether to include full element details (default: True)
    
    Returns:
        Dict containing:
        - count: Number of matching elements
        - elements: List of matching element details
        - summary: Brief description of results
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = filter_elements_by_property_and_keywords(
        ...     ifc_file=model,
        ...     element_type='IfcSpace',
        ...     property_filter={
        ...         'property_set': 'PSet_Revit_Constraints',
        ...         'property_name': 'Level',
        ...         'property_value': 'Second Floor'
        ...     },
        ...     keywords=['toilet', 'wc', 'restroom', 'bathroom']
        ... )
        >>> print(f"Found {result['count']} toilet rooms")
    """
    try:
        # Validate inputs
        if not isinstance(property_filter, dict) or not all(k in property_filter for k in ['property_set', 'property_name', 'property_value']):
            raise ValueError("property_filter must contain 'property_set', 'property_name', and 'property_value' keys")
        
        if not keywords:
            raise ValueError("keywords list cannot be empty")
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # First filter: by property value
        property_filtered_elements = []
        for element in elements:
            try:
                # Get the specific property value using ifcopenshell.util.element
                property_value = ifcopenshell.util.element.get_pset(
                    element, 
                    property_filter['property_set'], 
                    property_filter['property_name']
                )
                
                if property_value == property_filter['property_value']:
                    property_filtered_elements.append(element)
            except (AttributeError, KeyError):
                # Element doesn't have the required property, skip it
                continue
        
        # Second filter: by keywords in specified fields
        keyword_filtered_elements = []
        for element in property_filtered_elements:
            keyword_match = False
            
            # Check each search field for keyword matches
            for field in search_fields:
                if hasattr(element, field):
                    field_value = getattr(element, field)
                    if field_value is not None:
                        field_str = str(field_value)
                        
                        # Check if any keyword matches this field
                        for keyword in keywords:
                            if case_sensitive:
                                if keyword in field_str:
                                    keyword_match = True
                                    break
                            else:
                                if keyword.lower() in field_str.lower():
                                    keyword_match = True
                                    break
                        
                        if keyword_match:
                            break
            
            if keyword_match:
                keyword_filtered_elements.append(element)
        
        # Prepare results
        elements_details = []
        for element in keyword_filtered_elements:
            if include_details:
                element_info = {
                    'id': element.id(),
                    'type': element.is_a(),
                    'global_id': element.GlobalId if hasattr(element, 'GlobalId') else None
                }
                
                # Add search field values
                for field in search_fields:
                    if hasattr(element, field):
                        element_info[field] = getattr(element, field)
                
                # Add the filtering property value
                element_info[f"{property_filter['property_set']}.{property_filter['property_name']}"] = ifcopenshell.util.element.get_pset(
                    element, 
                    property_filter['property_set'], 
                    property_filter['property_name']
                )
                
                elements_details.append(element_info)
            else:
                elements_details.append({
                    'id': element.id(),
                    'type': element.is_a()
                })
        
        # Create summary
        summary = f"Found {len(keyword_filtered_elements)} {element_type} elements matching property '{property_filter['property_set']}.{property_filter['property_name']}' = '{property_filter['property_value']}' and keywords {keywords}"
        
        return {
            'count': len(keyword_filtered_elements),
            'elements': elements_details,
            'summary': summary
        }
        
    except Exception as e:
        return {
            'count': 0,
            'elements': [],
            'summary': f"Error: {str(e)}",
            'error': str(e)
        }