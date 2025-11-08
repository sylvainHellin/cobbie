import ifcopenshell
import re
from typing import Dict, List, Any, Union

def categorize_elements_by_naming_pattern(
    ifc_file: ifcopenshell.file,
    element_type: str,
    pattern_type: str,
    patterns: Dict[str, str],
    include_details: bool = True,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Categorizes and counts IFC elements based on naming patterns (prefixes, suffixes, or regex patterns).
    This function handles the common BIM practice of organizing elements by naming conventions
    that indicate units, zones, floors, or other classifications.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSpace', 'IfcDoor', 'IfcWall')
        pattern_type: Type of naming pattern ('prefix', 'suffix', or 'regex')
        patterns: Dict mapping category names to patterns (e.g., {'House A': 'A*', 'House B': 'B*'} for prefixes)
        include_details: Boolean to include detailed element information (default: True)
        case_sensitive: Boolean for case-sensitive matching (default: False)
    
    Returns:
        Dict containing:
        - total_count: Total number of elements processed
        - categories: Dict with counts per category
        - uncategorized: List of elements not matching any pattern
        - details: Optional detailed breakdown of elements per category
    
    Example usage:
        ```python
        import ifcopenshell
        model = ifcopenshell.open('model.ifc')
        result = categorize_elements_by_naming_pattern(
            model,
            'IfcSpace',
            'prefix',
            {'House A': 'A*', 'House B': 'B*'}
        )
        print(f"House A has {result['categories']['House A']} rooms")
        ```
    """
    try:
        # Validate inputs
        if not isinstance(ifc_file, ifcopenshell.file):
            raise ValueError("ifc_file must be a valid ifcopenshell.file object")
        
        if pattern_type not in ['prefix', 'suffix', 'regex']:
            raise ValueError("pattern_type must be 'prefix', 'suffix', or 'regex'")
        
        if not isinstance(patterns, dict) or not patterns:
            raise ValueError("patterns must be a non-empty dictionary")
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_count = len(elements)
        
        # Initialize result structure
        categories = {category: [] for category in patterns.keys()}
        uncategorized = []
        
        # Process each element
        for element in elements:
            element_name = element.Name if hasattr(element, 'Name') and element.Name else ''
            
            if not case_sensitive:
                element_name = element_name.lower()
            
            matched = False
            
            # Check against each pattern
            for category, pattern in patterns.items():
                check_pattern = pattern if case_sensitive else pattern.lower()
                
                if pattern_type == 'prefix':
                    if element_name.startswith(check_pattern.replace('*', '')):
                        categories[category].append(element)
                        matched = True
                        break
                elif pattern_type == 'suffix':
                    if element_name.endswith(check_pattern.replace('*', '')):
                        categories[category].append(element)
                        matched = True
                        break
                elif pattern_type == 'regex':
                    try:
                        if re.match(check_pattern, element_name):
                            categories[category].append(element)
                            matched = True
                            break
                    except re.error as e:
                        raise ValueError(f"Invalid regex pattern '{pattern}' for category '{category}': {e}")
            
            if not matched:
                uncategorized.append(element)
        
        # Build result
        result = {
            'total_count': total_count,
            'categories': {category: len(elements_list) for category, elements_list in categories.items()},
            'uncategorized': len(uncategorized)
        }
        
        # Add details if requested
        if include_details:
            details = {}
            for category, elements_list in categories.items():
                details[category] = [
                    {
                        'id': element.id,
                        'name': element.Name if hasattr(element, 'Name') else '',
                        'long_name': element.LongName if hasattr(element, 'LongName') else ''
                    }
                    for element in elements_list
                ]
            
            details['uncategorized'] = [
                {
                    'id': element.id,
                    'name': element.Name if hasattr(element, 'Name') else '',
                    'long_name': element.LongName if hasattr(element, 'LongName') else ''
                }
                for element in uncategorized
            ]
            
            result['details'] = details
        
        return result
        
    except Exception as e:
        raise RuntimeError(f"Error categorizing elements: {e}")