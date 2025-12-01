import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union
import statistics

def analyze_elements_by_property_with_dimensions(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    filter_property: str,
    filter_values: List[Union[str, bool, int, float]],
    dimension_properties: List[str],
    include_statistics: bool = True,
    include_individual_elements: bool = False,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes IFC elements filtered by property conditions and extracts their dimensional properties.
    
    This function handles the common BIM analysis pattern of finding elements that meet specific
    criteria (e.g., fire exits, accessible elements, performance-rated components) and extracting
    their measurements (width, height, length, area, volume) with aggregated statistics.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element types to analyze (e.g., ['IfcDoor', 'IfcWindow'])
        filter_property: Property name to filter by (e.g., 'IsFireExit', 'IsAccessible')
        filter_values: List of property values to match (e.g., [True, 'Yes', 1])
        dimension_properties: List of dimensional property names to extract (e.g., ['Width', 'Height', 'Length'])
        include_statistics: Boolean to include statistical analysis (default: True)
        include_individual_elements: Boolean to include individual element details (default: False)
        case_sensitive: Boolean for case-sensitive property matching (default: False)
    
    Returns:
        Dict containing:
        - matching_elements: List of elements that match the filter criteria
        - dimension_summary: Statistics for each dimensional property (min, max, average, count)
        - unique_values: Unique dimensional values with counts
        - individual_elements: Optional detailed information about each matching element
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = analyze_elements_by_property_with_dimensions(
        ...     ifc_file=model,
        ...     element_types=['IfcDoor'],
        ...     filter_property='IsFireExit',
        ...     filter_values=[True, 'IsFireExit'],
        ...     dimension_properties=['Width', 'Height']
        ... )
        >>> print(result['dimension_summary']['Width']['average'])
    """
    
    try:
        # Initialize result structure
        result = {
            'matching_elements': [],
            'dimension_summary': {},
            'unique_values': {},
            'individual_elements': [] if include_individual_elements else None
        }
        
        # Collect all dimensional values for statistics
        dimension_values = {prop: [] for prop in dimension_properties}
        
        # Prepare filter property name for case insensitive matching
        filter_property_cmp = filter_property if case_sensitive else filter_property.lower()
        
        # Process each element type
        for element_type in element_types:
            try:
                elements = ifc_file.by_type(element_type)
                
                for element in elements:
                    try:
                        # Get all property sets for the element
                        psets = ifcopenshell.util.element.get_psets(element)
                        
                        # Check if element matches filter criteria
                        matches_filter = False
                        property_found = False
                        
                        for pset_name, pset_data in psets.items():
                            # Check property name (case insensitive if needed)
                            prop_names = pset_data.keys() if case_sensitive else [k.lower() for k in pset_data.keys()]
                            
                            if filter_property_cmp in prop_names:
                                property_found = True
                                
                                # Get the actual property name (for case sensitive access)
                                if case_sensitive:
                                    actual_prop_name = filter_property
                                else:
                                    # Find the actual property name that matches case-insensitively
                                    for actual_name in pset_data.keys():
                                        if actual_name.lower() == filter_property_cmp:
                                            actual_prop_name = actual_name
                                            break
                                
                                property_value = pset_data[actual_prop_name]
                                
                                # Handle case sensitivity for property values
                                if not case_sensitive and isinstance(property_value, str):
                                    property_value_cmp = property_value.lower()
                                    filter_values_cmp = [str(v).lower() for v in filter_values if v is not None]
                                else:
                                    property_value_cmp = property_value
                                    filter_values_cmp = filter_values
                                
                                # Check if property value matches any filter value
                                # Special handling for None in filter_values (match any value)
                                if None in filter_values:
                                    matches_filter = True
                                elif property_value_cmp in filter_values_cmp:
                                    matches_filter = True
                                
                                if matches_filter:
                                    break
                        
                        # Only include element if property was found and matches filter
                        if property_found and matches_filter:
                            result['matching_elements'].append(element)
                            
                            # Extract dimensional properties
                            element_dimensions = {}
                            for dim_prop in dimension_properties:
                                dim_value = None
                                
                                # Search through all property sets for the dimensional property
                                for pset_name, pset_data in psets.items():
                                    # Check property name (case insensitive if needed)
                                    prop_names = pset_data.keys() if case_sensitive else [k.lower() for k in pset_data.keys()]
                                    dim_prop_cmp = dim_prop if case_sensitive else dim_prop.lower()
                                    
                                    if dim_prop_cmp in prop_names:
                                        # Get the actual property name
                                        if case_sensitive:
                                            actual_dim_name = dim_prop
                                        else:
                                            for actual_name in pset_data.keys():
                                                if actual_name.lower() == dim_prop_cmp:
                                                    actual_dim_name = actual_name
                                                    break
                                        
                                        dim_value = pset_data[actual_dim_name]
                                        # Convert to float if it's a numeric value
                                        if isinstance(dim_value, (int, float)):
                                            dim_value = float(dim_value)
                                        break
                                
                                element_dimensions[dim_prop] = dim_value
                                
                                # Collect for statistics if numeric
                                if dim_value is not None and isinstance(dim_value, (int, float)):
                                    dimension_values[dim_prop].append(dim_value)
                            
                            # Include individual element details if requested
                            if include_individual_elements:
                                element_info = {
                                    'id': element.id(),
                                    'type': element.is_a(),
                                    'name': getattr(element, 'Name', 'Unnamed'),
                                    'dimensions': element_dimensions
                                }
                                result['individual_elements'].append(element_info)
                    
                    except Exception as e:
                        # Continue processing other elements if one fails
                        continue
            
            except Exception as e:
                # Continue processing other element types if one fails
                continue
        
        # Calculate statistics if requested
        if include_statistics:
            for dim_prop, values in dimension_values.items():
                if values:  # Only calculate if we have values
                    result['dimension_summary'][dim_prop] = {
                        'count': len(values),
                        'min': min(values),
                        'max': max(values),
                        'average': statistics.mean(values),
                        'median': statistics.median(values)
                    }
                else:
                    result['dimension_summary'][dim_prop] = {
                        'count': 0,
                        'min': None,
                        'max': None,
                        'average': None,
                        'median': None
                    }
        
        # Calculate unique values with counts
        for dim_prop, values in dimension_values.items():
            if values:
                # Round values to handle floating point precision issues
                rounded_values = [round(v, 6) for v in values]
                unique_counts = {}
                for val in rounded_values:
                    unique_counts[val] = unique_counts.get(val, 0) + 1
                result['unique_values'][dim_prop] = unique_counts
            else:
                result['unique_values'][dim_prop] = {}
        
        return result
    
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'matching_elements': [],
            'dimension_summary': {},
            'unique_values': {},
            'individual_elements': None
        }