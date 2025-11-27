import ifcopenshell
import ifcopenshell.util.element
import re
from typing import List, Dict, Any, Union, Optional


def extract_dimensions_from_element_fields(
    ifc_file: ifcopenshell.file,
    element_type: str,
    source_fields: List[str] = ['ObjectType', 'Name'],
    dimension_patterns: Optional[List[str]] = None,
    target_dimensions: List[str] = ['width', 'height'],
    output_unit: str = 'm',
    aggregation: str = 'by_type',
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Extracts dimensional information (width, height, depth) from IFC element ObjectType, Name, or other text fields using flexible pattern matching.
    
    This function handles the common BIM analysis challenge where dimensions are embedded in naming conventions rather than stored in property sets.
    It parses various dimension formats (e.g., '762 x 2032mm', '0.8m x 2.1m', '800x2000'), performs unit conversions, and provides aggregated results.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcDoor', 'IfcWindow')
        source_fields: List of fields to search for dimensions (default: ['ObjectType', 'Name'])
        dimension_patterns: List of regex patterns for dimension formats (auto-generated if not provided)
        target_dimensions: List of dimensions to extract (default: ['width', 'height'])
        output_unit: Unit for output values (default: 'm', options: 'm', 'mm', 'cm')
        aggregation: How to aggregate results (default: 'by_type', options: 'all', 'by_type', 'by_level')
        include_details: Include individual element details (default: False)
    
    Returns:
        Dict containing:
        - 'elements_analyzed': Number of elements processed
        - 'dimensions_found': List of extracted dimension data
        - 'summary_by_type': Aggregated results by element type
        - 'unit_conversions_applied': Details of unit conversions performed
        - 'parsing_statistics': Success/failure rates for different patterns
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = extract_dimensions_from_element_fields(
        ...     model, 'IfcDoor', output_unit='m'
        ... )
        >>> print(result['summary_by_type'])
    """
    
    # Validate inputs
    if output_unit not in ['m', 'mm', 'cm']:
        raise ValueError("output_unit must be 'm', 'mm', or 'cm'")
    
    if aggregation not in ['all', 'by_type', 'by_level']:
        raise ValueError("aggregation must be 'all', 'by_type', or 'by_level'")
    
    # Default dimension patterns if not provided
    if dimension_patterns is None:
        dimension_patterns = [
            r'(\d+)\s*x\s*(\d+)\s*mm',  # 762 x 2032mm
            r'(\d+\.?\d*)\s*m\s*x\s*(\d+\.?\d*)\s*m',  # 0.8m x 2.1m
            r'(\d+)\s*x\s*(\d+)',  # 800x2000
            r'(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*cm',  # 80.0 x 210.0 cm
            r'(\d+)mm\s*x\s*(\d+)mm',  # 800mm x 2000mm
            r'(\d+)\s*mm\s*x\s*(\d+)\s*mm',  # 800 mm x 2000 mm
        ]
    
    # Unit conversion factors
    unit_conversions = {
        'm': {'mm': 0.001, 'cm': 0.01, 'm': 1.0},
        'mm': {'mm': 1.0, 'cm': 10.0, 'm': 1000.0},
        'cm': {'mm': 0.1, 'cm': 1.0, 'm': 100.0}
    }
    
    # Get elements of specified type
    try:
        elements = ifc_file.by_type(element_type)
    except Exception as e:
        raise ValueError(f"Invalid element type '{element_type}': {e}")
    
    elements_analyzed = len(elements)
    dimensions_found = []
    parsing_stats = {pattern: 0 for pattern in dimension_patterns}
    parsing_stats['failed'] = 0
    
    # Process each element
    for element in elements:
        element_info = {
            'id': element.id,
            'GlobalId': element.GlobalId,
            'Name': element.Name,
            'ObjectType': element.ObjectType,
            'type': element.is_a()
        }
        
        # Try to extract dimensions from each source field
        for field in source_fields:
            try:
                field_value = getattr(element, field, None)
                if field_value is None:
                    continue
                
                field_value_str = str(field_value)
                
                # Try each pattern
                for i, pattern in enumerate(dimension_patterns):
                    match = re.search(pattern, field_value_str, re.IGNORECASE)
                    if match:
                        # Extract dimensions
                        dims = [float(match.group(j + 1)) for j in range(len(match.groups()))]
                        
                        # Determine input unit from pattern
                        if 'mm' in pattern.lower():
                            input_unit = 'mm'
                        elif 'cm' in pattern.lower():
                            input_unit = 'cm'
                        elif 'm' in pattern.lower():
                            input_unit = 'm'
                        else:
                            input_unit = 'mm'  # Default assumption
                        
                        # Convert to output unit
                        conversion_factor = unit_conversions[output_unit][input_unit]
                        converted_dims = [d * conversion_factor for d in dims]
                        
                        # Create dimension result
                        dimension_result = {
                            'element_id': element.id,
                            'GlobalId': element.GlobalId,
                            'Name': element.Name,
                            'ObjectType': element.ObjectType,
                            'source_field': field,
                            'source_value': field_value_str,
                            'pattern_used': pattern,
                            'input_unit': input_unit,
                            'output_unit': output_unit,
                            'raw_values': dims,
                            'converted_values': converted_dims
                        }
                        
                        # Map to target dimensions
                        dim_mapping = {}
                        for j, dim_name in enumerate(target_dimensions):
                            if j < len(converted_dims):
                                dim_mapping[dim_name] = converted_dims[j]
                        
                        dimension_result['dimensions'] = dim_mapping
                        dimensions_found.append(dimension_result)
                        parsing_stats[pattern] += 1
                        break  # Stop after first successful match
                else:
                    # No pattern matched for this field
                    continue
                break  # Stop after first successful field
            except Exception as e:
                continue
        else:
            # No field yielded dimensions
            parsing_stats['failed'] += 1
    
    # Aggregate results
    summary_by_type = {}
    
    if aggregation == 'by_type':
        # Group by ObjectType
        for dim in dimensions_found:
            obj_type = dim.get('ObjectType', 'Unknown')
            if obj_type not in summary_by_type:
                summary_by_type[obj_type] = {
                    'count': 0,
                    'dimensions': [],
                    'elements': []
                }
            
            summary_by_type[obj_type]['count'] += 1
            summary_by_type[obj_type]['dimensions'].append(dim['dimensions'])
            if include_details:
                summary_by_type[obj_type]['elements'].append(dim)
    
    elif aggregation == 'all':
        # All elements together
        all_dims = [dim['dimensions'] for dim in dimensions_found]
        summary_by_type['all'] = {
            'count': len(dimensions_found),
            'dimensions': all_dims
        }
        if include_details:
            summary_by_type['all']['elements'] = dimensions_found
    
    # Calculate unit conversion details
    unit_conversions_applied = {
        'target_unit': output_unit,
        'conversions_used': set()
    }
    
    for dim in dimensions_found:
        unit_conversions_applied['conversions_used'].add(
            f"{dim['input_unit']} -> {dim['output_unit']}"
        )
    
    unit_conversions_applied['conversions_used'] = list(unit_conversions_applied['conversions_used'])
    
    return {
        'elements_analyzed': elements_analyzed,
        'dimensions_found': dimensions_found if include_details else [],
        'summary_by_type': summary_by_type,
        'unit_conversions_applied': unit_conversions_applied,
        'parsing_statistics': parsing_stats
    }