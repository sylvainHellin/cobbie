import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Tuple, Optional, Any, Union, Callable
import json

def analyze_element_types_and_distribution(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    type_property_sources: List[Tuple[str, Optional[str]]] = [('Text', 'Filtertyp'), ('Pset_DoorTypeCommon', 'Type'), ('ObjectType', None)],
    include_spatial_distribution: bool = True,
    include_detailed_properties: bool = False,
    max_examples_per_type: int = 3,
    spatial_check_methods: List[str] = ['relationships', 'properties', 'geometry'],
    level_property_sources: List[Tuple[str, str]] = [('Abhängigkeiten', 'Ebene'), ('Pset_SpaceCommon', 'Level')],
    include_indirect_containment: bool = True,
    # New optional parameters for extended functionality
    include_type_validation: bool = False,
    valid_types: Optional[List[str]] = None,
    custom_type_mapping: Optional[Callable[[Any], str]] = None,
    aggregate_by_system: bool = False,
    include_quantities: bool = False,
    filter_by_level: Optional[List[str]] = None,
    system_property_sources: List[Tuple[str, str]] = [('HLS', 'Systemname'), ('Pset_DistributionSystemCommon', 'SystemName')]
) -> Dict[str, Any]:
    """
    Analyzes IFC elements to discover their types, counts, and spatial distribution by building levels.
    
    This function answers questions like 'what types of filters/doors/windows are used, their counts,
    and how are they distributed by floor?' by combining element discovery, property-based categorization,
    and spatial analysis.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element types to analyze (e.g., ['IfcFilter', 'IfcDoor'])
        type_property_sources: List of (property_set, property_name) tuples to extract type information.
                           If property_name is None, uses the property set name as the type.
                           Default: [('Text', 'Filtertyp'), ('Pset_DoorTypeCommon', 'Type'), ('ObjectType', None)]
        include_spatial_distribution: Boolean to include level-based distribution (default: True)
        include_detailed_properties: Boolean to include full property details (default: False)
        max_examples_per_type: Maximum number of example elements to include per type (default: 3)
        spatial_check_methods: List of methods to use for finding element levels.
                              Options: 'relationships', 'properties', 'geometry'
                              Default: ['relationships', 'properties', 'geometry']
        level_property_sources: List of (property_set, property_name) tuples for property-based level detection.
                                Default: [('Abhängigkeiten', 'Ebene'), ('Pset_SpaceCommon', 'Level')]
        include_indirect_containment: Boolean to handle elements contained in spaces that are contained in levels.
                                     Default: True
        include_type_validation: Boolean to validate discovered types against valid_types list (default: False)
        valid_types: Optional list of valid type names for validation (default: None)
        custom_type_mapping: Optional custom function to map elements to type names (default: None)
        aggregate_by_system: Boolean to group elements by system classification (default: False)
        include_quantities: Boolean to include quantity takeoff data (default: False)
        filter_by_level: Optional list of level names to filter elements by (default: None)
        system_property_sources: List of (property_set, property_name) tuples for system classification.
                                Default: [('HLS', 'Systemname'), ('Pset_DistributionSystemCommon', 'SystemName')]
    
    Returns:
        Dict containing:
        - 'element_types_found': List of element types that were found in the model
        - 'total_elements': Total count of all analyzed elements
        - 'elements_by_type': Dict with element type as key and analysis results as value
        - 'spatial_distribution': Dict with building level names as keys and element counts as values
        - 'type_summary': Dict with discovered subtypes and their counts across all element types
        - 'system_aggregation': Dict with system names as keys and element counts (if aggregate_by_system=True)
        - 'quantities_summary': Dict with quantity data (if include_quantities=True)
        - 'validation_results': Dict with type validation results (if include_type_validation=True)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('ventilation.ifc')
        >>> result = analyze_element_types_and_distribution(
        ...     model, 
        ...     ['IfcFilter'],
        ...     type_property_sources=[('Text', 'Filtertyp'), ('ObjectType', None)]
        ... )
        >>> print(result['elements_by_type']['IfcFilter']['type_counts'])
        {'F7': 2}
    """
    # Initialize result structure to ensure consistent return type
    result = {
        'element_types_found': [],
        'total_elements': 0,
        'elements_by_type': {},
        'spatial_distribution': {},
        'type_summary': {}
    }
    
    # Add optional result sections
    if aggregate_by_system:
        result['system_aggregation'] = {}
    if include_quantities:
        result['quantities_summary'] = {}
    if include_type_validation:
        result['validation_results'] = {'valid_count': 0, 'invalid_count': 0, 'invalid_types': []}
    
    try:
        # Analyze each element type
        for element_type in element_types:
            try:
                elements = ifc_file.by_type(element_type)
                if not elements:
                    continue
                    
                result['element_types_found'].append(element_type)
                element_count = len(elements)
                result['total_elements'] += element_count
                
                # Initialize analysis data for this element type
                type_analysis = {
                    'count': element_count,
                    'type_counts': {},  # Discovered subtypes and their counts
                    'spatial_distribution': {},  # Distribution by building level
                    'examples': []  # Example elements
                }
                
                # Add optional analysis sections
                if aggregate_by_system:
                    type_analysis['system_distribution'] = {}
                if include_quantities:
                    type_analysis['quantities'] = {}
                
                # Process each element
                for element in elements:
                    # Apply level filter if specified
                    if filter_by_level:
                        element_level = None
                        for method in spatial_check_methods:
                            if method == 'relationships':
                                try:
                                    container = ifcopenshell.util.element.get_container(element)
                                    if container and hasattr(container, 'Name') and container.is_a('IfcBuildingStorey'):
                                        element_level = container.Name
                                        break
                                except:
                                    continue
                            elif method == 'properties':
                                for prop_set_name, prop_name in level_property_sources:
                                    try:
                                        prop_value = ifcopenshell.util.element.get_pset(element, prop_set_name, prop_name)
                                        if prop_value is not None:
                                            element_level = str(prop_value)
                                            break
                                    except:
                                        continue
                        
                        if element_level not in filter_by_level:
                            continue  # Skip this element
                    
                    # Extract type information
                    element_type_name = None
                    
                    # Use custom type mapping if provided
                    if custom_type_mapping:
                        try:
                            element_type_name = custom_type_mapping(element)
                        except:
                            pass
                    
                    # Standard type extraction if custom mapping didn't work
                    if element_type_name is None:
                        for prop_set_name, prop_name in type_property_sources:
                            try:
                                if prop_name is None:
                                    psets = ifcopenshell.util.element.get_psets(element)
                                    if prop_set_name in psets:
                                        element_type_name = prop_set_name
                                        break
                                else:
                                    prop_value = ifcopenshell.util.element.get_pset(element, prop_set_name, prop_name)
                                    if prop_value is not None:
                                        element_type_name = str(prop_value)
                                        break
                            except:
                                continue
                    
                    # Fallback to ObjectType or predefined type
                    if element_type_name is None:
                        if hasattr(element, 'ObjectType') and element.ObjectType:
                            element_type_name = str(element.ObjectType)
                        elif hasattr(element, 'PredefinedType') and element.PredefinedType:
                            element_type_name = str(element.PredefinedType)
                        else:
                            element_type_name = 'Unknown'
                    
                    # Type validation if enabled
                    if include_type_validation and valid_types:
                        if element_type_name in valid_types:
                            result['validation_results']['valid_count'] += 1
                        else:
                            result['validation_results']['invalid_count'] += 1
                            if element_type_name not in result['validation_results']['invalid_types']:
                                result['validation_results']['invalid_types'].append(element_type_name)
                    
                    # Count the discovered type
                    if element_type_name not in type_analysis['type_counts']:
                        type_analysis['type_counts'][element_type_name] = 0
                    type_analysis['type_counts'][element_type_name] += 1
                    
                    # Update global type summary
                    if element_type_name not in result['type_summary']:
                        result['type_summary'][element_type_name] = 0
                    result['type_summary'][element_type_name] += 1
                    
                    # System aggregation if enabled
                    if aggregate_by_system:
                        system_name = None
                        for prop_set_name, prop_name in system_property_sources:
                            try:
                                prop_value = ifcopenshell.util.element.get_pset(element, prop_set_name, prop_name)
                                if prop_value is not None:
                                    system_name = str(prop_value)
                                    break
                            except:
                                continue
                        
                        if system_name:
                            if system_name not in type_analysis['system_distribution']:
                                type_analysis['system_distribution'][system_name] = {}
                            if element_type_name not in type_analysis['system_distribution'][system_name]:
                                type_analysis['system_distribution'][system_name][element_type_name] = 0
                            type_analysis['system_distribution'][system_name][element_type_name] += 1
                            
                            if system_name not in result['system_aggregation']:
                                result['system_aggregation'][system_name] = 0
                            result['system_aggregation'][system_name] += 1
                    
                    # Quantities if enabled
                    if include_quantities:
                        try:
                            qtos = ifcopenshell.util.element.get_qtos(element)
                            if qtos:
                                element_qtos = {}
                                for qto_name, qto_data in qtos.items():
                                    element_qtos[qto_name] = qto_data
                                type_analysis['quantities'][element.id()] = element_qtos
                        except:
                            pass
                    
                    # Spatial distribution analysis
                    if include_spatial_distribution:
                        level_name = None
                        
                        # Method 1: Use relationships
                        if 'relationships' in spatial_check_methods:
                            try:
                                container = ifcopenshell.util.element.get_container(element)
                                if container and hasattr(container, 'Name'):
                                    if container.is_a('IfcBuildingStorey'):
                                        level_name = container.Name
                                    elif include_indirect_containment and container.is_a('IfcSpace'):
                                        space_container = ifcopenshell.util.element.get_container(container)
                                        if space_container and space_container.is_a('IfcBuildingStorey') and hasattr(space_container, 'Name'):
                                            level_name = space_container.Name
                            except:
                                pass
                        
                        # Method 2: Use properties
                        if level_name is None and 'properties' in spatial_check_methods:
                            for prop_set_name, prop_name in level_property_sources:
                                try:
                                    prop_value = ifcopenshell.util.element.get_pset(element, prop_set_name, prop_name)
                                    if prop_value is not None:
                                        level_name = str(prop_value)
                                        break
                                except:
                                    continue
                        
                        # Update spatial distribution if level found
                        if level_name:
                            if level_name not in type_analysis['spatial_distribution']:
                                type_analysis['spatial_distribution'][level_name] = {}
                            if element_type_name not in type_analysis['spatial_distribution'][level_name]:
                                type_analysis['spatial_distribution'][level_name][element_type_name] = 0
                            type_analysis['spatial_distribution'][level_name][element_type_name] += 1
                            
                            if level_name not in result['spatial_distribution']:
                                result['spatial_distribution'][level_name] = 0
                            result['spatial_distribution'][level_name] += 1
                    
                    # Add example elements
                    if len(type_analysis['examples']) < max_examples_per_type:
                        example_data = {
                            'id': element.id(),
                            'name': getattr(element, 'Name', 'Unnamed'),
                            'discovered_type': element_type_name
                        }
                        
                        if include_detailed_properties:
                            try:
                                psets = ifcopenshell.util.element.get_psets(element)
                                example_data['property_sets'] = psets
                            except:
                                example_data['property_sets'] = {}
                        
                        type_analysis['examples'].append(example_data)
                
                result['elements_by_type'][element_type] = type_analysis
                
            except Exception as e:
                # Continue with next element type if one fails
                continue
        
        return result
        
    except Exception as e:
        # Always return a dictionary, even in case of error
        return {
            'error': str(e),
            'element_types_found': result.get('element_types_found', []),
            'total_elements': result.get('total_elements', 0),
            'elements_by_type': result.get('elements_by_type', {}),
            'spatial_distribution': result.get('spatial_distribution', {}),
            'type_summary': result.get('type_summary', {})
        }