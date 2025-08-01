
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any
import re

def count_light_fixtures(
    ifc_file_path: str, 
    include_types: List[str] = None, 
    name_patterns: List[str] = None
) -> Dict[str, Any]:
    """
    Count light fixtures in an IFC model by searching for elements with lighting-related names.
    
    This function is designed to work with IFC2X3 schema where IfcLightFixture entity type
    may not be available. It searches for elements by name patterns related to lighting.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        include_types (List[str], optional): IFC types to include in search. 
            Defaults to ['IfcLightFixture', 'IfcLamp'].
        name_patterns (List[str], optional): Name patterns to search for. 
            Defaults to ['light', 'lamp', 'pendant', 'sconce'].
            
    Returns:
        Dict[str, Any]: Dictionary containing:
            - total_count: Total number of light fixtures found
            - by_pattern: Dictionary with counts for each pattern
            - by_type: Dictionary with counts for each IFC type (if found)
            - elements: List of found elements with their names and types
    
    Note:
        For IFC2X3 models, this function primarily relies on name-based searches
        as IfcLightFixture entity may not be available in this schema version.
    """
    if include_types is None:
        include_types = ['IfcLightFixture', 'IfcLamp']
    
    if name_patterns is None:
        name_patterns = ['light', 'lamp', 'pendant', 'sconce']
    
    # Load the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Initialize results
    results = {
        'total_count': 0,
        'by_pattern': {},
        'by_type': {},
        'elements': []
    }
    
    # Search by IFC types (if available in the schema)
    for ifc_type in include_types:
        try:
            elements = model.by_type(ifc_type)
            results['by_type'][ifc_type] = len(elements)
            results['total_count'] += len(elements)
            
            # Add elements to the list
            for element in elements:
                results['elements'].append({
                    'name': getattr(element, 'Name', 'Unnamed'),
                    'type': element.is_a(),
                    'id': element.id()
                })
        except RuntimeError:
            # Type not found in schema (common with IFC2X3)
            results['by_type'][ifc_type] = 0
            continue
    
    # Search by name patterns
    all_elements = model.by_type("IfcElement")
    
    # Keep track of already counted elements to avoid duplicates
    counted_elements = set()
    
    for pattern in name_patterns:
        results['by_pattern'][pattern] = 0
        pattern_elements = []
        
        for element in all_elements:
            element_name = getattr(element, 'Name', None)
            if element_name and pattern.lower() in element_name.lower():
                # Check if we've already counted this element
                element_key = (element.id(), element_name)
                if element_key not in counted_elements:
                    pattern_elements.append({
                        'name': element_name,
                        'type': element.is_a(),
                        'id': element.id()
                    })
                    counted_elements.add(element_key)
        
        results['by_pattern'][pattern] = len(pattern_elements)
        
        # Add to total count (avoiding double counting)
        if pattern == name_patterns[0]:  # First pattern contributes to total
            results['total_count'] += len(pattern_elements)
    
    # Recalculate total count based on unique elements
    results['total_count'] = len(counted_elements)
    
    return results
