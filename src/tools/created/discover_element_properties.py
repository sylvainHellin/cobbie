import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional


def discover_element_properties(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_keywords: Optional[List[str]] = None,
    include_property_values: bool = False,
    max_elements_to_analyze: int = 50,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Discovers and catalogs all property sets and properties available for a specific IFC element type in a model.
    
    This function systematically explores all property sets and their properties for a given element type,
    with optional keyword filtering and value sampling. It's particularly useful for model exploration
    and understanding data structure before performing targeted property queries.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcDoor', 'IfcWall')
        property_keywords: Optional list of keywords to filter properties (e.g., ['fire', 'thermal'])
        include_property_values: Whether to sample actual property values (default: False)
        max_elements_to_analyze: Limit number of elements to analyze for performance (default: 50)
        case_sensitive: Whether keyword matching is case sensitive (default: False)
    
    Returns:
        Dict containing:
        - total_elements: Number of elements found
        - elements_analyzed: Number of elements actually analyzed
        - property_sets: Dict of property set names with their properties
        - filtered_properties: List of properties matching keywords (if keywords provided)
        - property_frequency: How often each property appears across elements
        - sample_values: Sample property values (if include_property_values=True)
        - standard_property_sets: Property sets that follow standard naming conventions (Pset_*)
        - type_property_sets: Property sets that appear to be type-specific
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = discover_element_properties(model, 'IfcDoor', ['fire'])
        >>> print(result['property_sets'])
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_elements = len(elements)
        
        if total_elements == 0:
            return {
                'total_elements': 0,
                'elements_analyzed': 0,
                'property_sets': {},
                'property_frequency': {},
                'sample_values': {},
                'filtered_properties': [],
                'standard_property_sets': {},
                'type_property_sets': {}
            }
        
        # Limit the number of elements to analyze
        elements_to_analyze = elements[:max_elements_to_analyze]
        elements_analyzed = len(elements_to_analyze)
        
        # Initialize result structures
        all_property_sets = {}
        property_frequency = {}
        sample_values = {}
        filtered_properties = []
        
        # Process each element
        for element in elements_to_analyze:
            try:
                # Get all property sets for this element
                psets = ifcopenshell.util.element.get_psets(element)
                
                for pset_name, pset_data in psets.items():
                    # Initialize property set if not seen before
                    if pset_name not in all_property_sets:
                        all_property_sets[pset_name] = set()
                    
                    # Process each property in the property set
                    for prop_name, prop_value in pset_data.items():
                        # Skip 'id' property as it's internal
                        if prop_name == 'id':
                            continue
                            
                        # Add property to the property set
                        all_property_sets[pset_name].add(prop_name)
                        
                        # Track property frequency
                        prop_key = f"{pset_name}.{prop_name}"
                        property_frequency[prop_key] = property_frequency.get(prop_key, 0) + 1
                        
                        # Sample values if requested
                        if include_property_values:
                            if prop_key not in sample_values:
                                sample_values[prop_key] = []
                            if len(sample_values[prop_key]) < 3:  # Limit to 3 samples per property
                                # Handle different value types for serialization
                                try:
                                    if hasattr(prop_value, 'wrappedValue'):
                                        value = prop_value.wrappedValue
                                    else:
                                        value = prop_value
                                    sample_values[prop_key].append(value)
                                except:
                                    sample_values[prop_key].append(str(prop_value))
                        
                        # Check for keyword matches
                        if property_keywords:
                            for keyword in property_keywords:
                                if case_sensitive:
                                    if keyword in prop_name:
                                        filtered_properties.append({
                                            'property_set': pset_name,
                                            'property_name': prop_name,
                                            'keyword_match': keyword
                                        })
                                else:
                                    if keyword.lower() in prop_name.lower():
                                        filtered_properties.append({
                                            'property_set': pset_name,
                                            'property_name': prop_name,
                                            'keyword_match': keyword
                                        })
            except Exception as e:
                # Continue processing other elements if one fails
                continue
        
        # Convert sets to lists for JSON serialization
        property_sets_serializable = {}
        for pset_name, props in all_property_sets.items():
            property_sets_serializable[pset_name] = sorted(list(props))
        
        # Categorize property sets
        standard_property_sets = {}
        type_property_sets = {}
        
        for pset_name, props in property_sets_serializable.items():
            if pset_name.startswith('Pset_'):
                standard_property_sets[pset_name] = props
            else:
                type_property_sets[pset_name] = props
        
        # Prepare result
        result = {
            'total_elements': total_elements,
            'elements_analyzed': elements_analyzed,
            'property_sets': property_sets_serializable,
            'property_frequency': property_frequency,
            'sample_values': sample_values if include_property_values else {},
            'filtered_properties': filtered_properties if property_keywords else [],
            'standard_property_sets': standard_property_sets,
            'type_property_sets': type_property_sets
        }
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'total_elements': 0,
            'elements_analyzed': 0,
            'property_sets': {},
            'property_frequency': {},
            'sample_values': {},
            'filtered_properties': [],
            'standard_property_sets': {},
            'type_property_sets': {}
        }