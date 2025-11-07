import ifcopenshell
from typing import List, Dict, Any, Optional, Tuple

def count_elements_by_multiple_types(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    include_details: bool = False,
    sort_by_count: bool = True
) -> Dict[str, Any]:
    """
    Counts IFC elements of multiple specified types and returns a summary with totals and optional details.
    
    This function efficiently counts elements across multiple IFC types in a single operation,
    designed for model composition analysis and element inventory tasks.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element type strings to count (e.g., ['IfcColumn', 'IfcBeam', 'IfcSlab'])
        include_details: Optional boolean to include sample elements for each type (default: False)
        sort_by_count: Optional boolean to sort results by count (default: True)
    
    Returns:
        Dict with:
        - 'element_counts': Dict mapping element_type -> count
        - 'total_elements': Total count across all specified types
        - 'elements_by_type': Optional dict of element details if include_details=True
        - 'summary': List of (element_type, count) tuples sorted by count
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = count_elements_by_multiple_types(
        ...     model, 
        ...     ['IfcColumn', 'IfcBeam', 'IfcSlab'],
        ...     include_details=True
        ... )
        >>> print(result['element_counts'])
        {'IfcColumn': 39, 'IfcBeam': 117, 'IfcSlab': 49}
    """
    try:
        # Initialize result dictionary
        result = {
            'element_counts': {},
            'total_elements': 0,
            'elements_by_type': {},
            'summary': []
        }
        
        # Process each element type
        for element_type in element_types:
            try:
                # Get all elements of this type
                elements = ifc_file.by_type(element_type)
                count = len(elements)
                
                # Store count
                result['element_counts'][element_type] = count
                result['total_elements'] += count
                
                # Include details if requested
                if include_details and elements:
                    element_details = []
                    for element in elements[:5]:  # Limit to first 5 for performance
                        detail = {
                            'id': element.id(),
                            'Name': getattr(element, 'Name', None),
                            'ObjectType': getattr(element, 'ObjectType', None),
                            'GlobalId': getattr(element, 'GlobalId', None)
                        }
                        element_details.append(detail)
                    result['elements_by_type'][element_type] = element_details
                    
            except Exception as e:
                # Handle cases where element type doesn't exist
                result['element_counts'][element_type] = 0
                if include_details:
                    result['elements_by_type'][element_type] = []
        
        # Create summary sorted by count if requested
        if sort_by_count:
            result['summary'] = sorted(
                result['element_counts'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )
        else:
            result['summary'] = list(result['element_counts'].items())
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'element_counts': {},
            'total_elements': 0,
            'elements_by_type': {},
            'summary': [],
            'error': str(e)
        }