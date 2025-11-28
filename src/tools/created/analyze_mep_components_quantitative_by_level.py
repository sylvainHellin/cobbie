import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Tuple, Callable, Optional, Any, Union
import math

def analyze_mep_components_quantitative_by_level(
    ifc_file,
    element_types: List[str],
    primary_property_sources: List[Tuple[str, str]],
    dimension_property_sources: List[Tuple[str, str]],
    spatial_property_source: Tuple[str, str],
    calculation_method: Optional[Callable[[Dict[str, float]], float]] = None,
    output_unit: str = 'm²',
    include_individual_elements: bool = False
) -> Dict[str, Any]:
    """
    Analyzes quantitative properties of MEP system components grouped by building level with comprehensive property extraction and fallback calculations.
    
    This function handles the common BIM analysis pattern of extracting quantitative data (areas, volumes, lengths) 
    from MEP components, calculating missing values from dimensions, and providing statistical breakdowns by spatial location.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element types to analyze (e.g., ['IfcDuctSegment', 'IfcDuctFitting'])
        primary_property_sources: List of (property_set, property_name) tuples for direct quantitative values 
            (e.g., [('HLS', 'Fläche')])
        dimension_property_sources: List of (property_set, property_name) tuples for dimensions used in fallback 
            calculations (e.g., [('Abmessungen', 'Breite'), ('Abmessungen', 'Höhe')])
        spatial_property_source: Tuple of (property_set, property_name) for level identification 
            (e.g., ('Abhängigkeiten', 'Referenzebene'))
        calculation_method: Function to calculate quantitative value from dimensions 
            (default: width * height for areas)
        output_unit: Unit for output values (default: 'm²')
        include_individual_elements: Boolean to include detailed element data (default: False)
    
    Returns:
        Dict containing:
        - total_count: Total number of elements analyzed
        - elements_with_data: Number of elements with quantitative data
        - total_value: Total quantitative value across all elements
        - average_value: Average value per element
        - breakdown_by_level: Dict with level-wise statistics
        - individual_elements: List of individual element data (if include_individual_elements=True)
        - output_unit: Unit string for output values
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('ventilation.ifc')
        >>> result = analyze_mep_components_quantitative_by_level(
        ...     model,
        ...     ['IfcDuctSegment', 'IfcDuctFitting'],
        ...     [('HLS', 'Fläche')],
        ...     [('Abmessungen', 'Breite'), ('Abmessungen', 'Höhe')],
        ...     ('Abhängigkeiten', 'Referenzebene')
        ... )
        >>> print(f"Total area: {result['total_value']:.2f} {result['output_unit']}")
    """
    
    # Set default calculation method for area (width * height)
    if calculation_method is None:
        calculation_method = lambda dims: dims.get('width', 0) * dims.get('height', 0)
    
    # Initialize result structure
    result = {
        'total_count': 0,
        'elements_with_data': 0,
        'total_value': 0.0,
        'average_value': 0.0,
        'breakdown_by_level': {},
        'individual_elements': [],
        'output_unit': output_unit
    }
    
    try:
        # Get all elements of specified types
        all_elements = []
        for element_type in element_types:
            try:
                elements = ifc_file.by_type(element_type)
                all_elements.extend(elements)
            except Exception as e:
                print(f"Warning: Could not retrieve elements of type {element_type}: {e}")
                continue
        
        result['total_count'] = len(all_elements)
        
        # Process each element
        for element in all_elements:
            element_data = {
                'id': getattr(element, 'GlobalId', None),
                'name': getattr(element, 'Name', None),
                'type': element.is_a(),
                'quantitative_value': None,
                'level': None,
                'dimensions': {},
                'data_source': None
            }
            
            try:
                # Get property sets using the recommended utility function
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Extract primary quantitative values
                for pset_name, prop_name in primary_property_sources:
                    if pset_name in psets and prop_name in psets[pset_name]:
                        value = psets[pset_name][prop_name]
                        if value is not None:
                            try:
                                # Handle different value types (IfcLengthMeasure, IfcAreaMeasure, etc.)
                                if hasattr(value, 'wrappedValue'):
                                    element_data['quantitative_value'] = float(value.wrappedValue)
                                else:
                                    element_data['quantitative_value'] = float(value)
                                element_data['data_source'] = f"{pset_name}.{prop_name}"
                                break
                            except (ValueError, TypeError):
                                continue
                
                # Extract dimensions for fallback calculation
                for pset_name, prop_name in dimension_property_sources:
                    if pset_name in psets and prop_name in psets[pset_name]:
                        value = psets[pset_name][prop_name]
                        if value is not None:
                            try:
                                if hasattr(value, 'wrappedValue'):
                                    dim_value = float(value.wrappedValue)
                                else:
                                    dim_value = float(value)
                                
                                # Convert mm to m for common dimensions
                                if prop_name.lower() in ['breite', 'höhe', 'width', 'height', 'länge', 'length']:
                                    dim_value = dim_value / 1000.0
                                
                                # Store dimension with standardized key
                                dim_key = prop_name.lower()
                                if 'breite' in dim_key or 'width' in dim_key:
                                    element_data['dimensions']['width'] = dim_value
                                elif 'höhe' in dim_key or 'height' in dim_key:
                                    element_data['dimensions']['height'] = dim_value
                                elif 'länge' in dim_key or 'length' in dim_key:
                                    element_data['dimensions']['length'] = dim_value
                                else:
                                    element_data['dimensions'][dim_key] = dim_value
                            except (ValueError, TypeError):
                                continue
                
                # Calculate value from dimensions if not found directly
                if element_data['quantitative_value'] is None and element_data['dimensions']:
                    try:
                        calculated_value = calculation_method(element_data['dimensions'])
                        if calculated_value > 0:
                            element_data['quantitative_value'] = calculated_value
                            element_data['data_source'] = 'calculated_from_dimensions'
                    except Exception:
                        pass
                
                # Extract level information
                pset_name, prop_name = spatial_property_source
                if pset_name in psets and prop_name in psets[pset_name]:
                    level_value = psets[pset_name][prop_name]
                    if level_value is not None:
                        level_str = str(level_value)
                        # Extract level name from 'Ebene: E02_OKRD' format
                        if ':' in level_str:
                            element_data['level'] = level_str.split(':')[1].strip()
                        else:
                            element_data['level'] = level_str.strip()
                
                # Fallback: use spatial container if property-based level extraction fails
                if element_data['level'] is None:
                    try:
                        container = ifcopenshell.util.element.get_container(element)
                        if container and hasattr(container, 'Name'):
                            element_data['level'] = container.Name
                    except Exception:
                        element_data['level'] = 'Unknown'
                
                # Process element if it has quantitative data
                if element_data['quantitative_value'] is not None:
                    result['elements_with_data'] += 1
                    result['total_value'] += element_data['quantitative_value']
                    
                    # Group by level
                    level = element_data['level'] or 'Unknown'
                    if level not in result['breakdown_by_level']:
                        result['breakdown_by_level'][level] = {
                            'count': 0,
                            'total_value': 0.0,
                            'values': []
                        }
                    
                    result['breakdown_by_level'][level]['count'] += 1
                    result['breakdown_by_level'][level]['total_value'] += element_data['quantitative_value']
                    result['breakdown_by_level'][level]['values'].append(element_data['quantitative_value'])
                    
                    # Include individual element data if requested
                    if include_individual_elements:
                        result['individual_elements'].append(element_data)
            
            except Exception as e:
                print(f"Warning: Error processing element {element_data['id']}: {e}")
                continue
        
        # Calculate average value
        if result['elements_with_data'] > 0:
            result['average_value'] = result['total_value'] / result['elements_with_data']
        
        # Calculate level averages
        for level_data in result['breakdown_by_level'].values():
            if level_data['count'] > 0:
                level_data['average_value'] = level_data['total_value'] / level_data['count']
            else:
                level_data['average_value'] = 0.0
        
        # Remove individual values list to reduce memory usage if not needed
        if not include_individual_elements:
            for level_data in result['breakdown_by_level'].values():
                level_data.pop('values', None)
    
    except Exception as e:
        print(f"Error in analyze_mep_components_quantitative_by_level: {e}")
        raise
    
    return result