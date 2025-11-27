import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Tuple, Optional, Any
import json

def analyze_element_types_and_distribution(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    type_property_sources: List[Tuple[str, Optional[str]]] = [('Text', 'Filtertyp'), ('Pset_DoorTypeCommon', 'Type'), ('ObjectType', None)],
    include_spatial_distribution: bool = True,
    include_detailed_properties: bool = False,
    max_examples_per_type: int = 3
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
    
    Returns:
        Dict containing:
        - 'element_types_found': List of element types that were found in the model
        - 'total_elements': Total count of all analyzed elements
        - 'elements_by_type': Dict with element type as key and analysis results as value
        - 'spatial_distribution': Dict with building level names as keys and element counts as values
        - 'type_summary': Dict with discovered subtypes and their counts across all element types
    
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
    try:
        result = {
            'element_types_found': [],
            'total_elements': 0,
            'elements_by_type': {},
            'spatial_distribution': {},
            'type_summary': {}
        }
        
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
                
                # Process each element
                for element in elements:
                    # Extract type information from property sources
                    element_type_name = None
                    
                    for prop_set_name, prop_name in type_property_sources:
                        try:
                            if prop_name is None:
                                # Use property set name as type indicator
                                psets = ifcopenshell.util.element.get_psets(element)
                                if prop_set_name in psets:
                                    element_type_name = prop_set_name
                                    break
                            else:
                                # Get specific property value
                                prop_value = ifcopenshell.util.element.get_pset(element, prop_set_name, prop_name)
                                if prop_value is not None:
                                    element_type_name = str(prop_value)
                                    break
                        except:
                            continue
                    
                    # Fallback to ObjectType or predefined type if no property found
                    if element_type_name is None:
                        if hasattr(element, 'ObjectType') and element.ObjectType:
                            element_type_name = str(element.ObjectType)
                        elif hasattr(element, 'PredefinedType') and element.PredefinedType:
                            element_type_name = str(element.PredefinedType)
                        else:
                            element_type_name = 'Unknown'
                    
                    # Count the discovered type
                    if element_type_name not in type_analysis['type_counts']:
                        type_analysis['type_counts'][element_type_name] = 0
                    type_analysis['type_counts'][element_type_name] += 1
                    
                    # Update global type summary
                    if element_type_name not in result['type_summary']:
                        result['type_summary'][element_type_name] = 0
                    result['type_summary'][element_type_name] += 1
                    
                    # Spatial distribution analysis
                    if include_spatial_distribution:
                        try:
                            container = ifcopenshell.util.element.get_container(element)
                            if container and hasattr(container, 'Name'):
                                level_name = container.Name
                                
                                # Update element type spatial distribution
                                if level_name not in type_analysis['spatial_distribution']:
                                    type_analysis['spatial_distribution'][level_name] = {}
                                if element_type_name not in type_analysis['spatial_distribution'][level_name]:
                                    type_analysis['spatial_distribution'][level_name][element_type_name] = 0
                                type_analysis['spatial_distribution'][level_name][element_type_name] += 1
                                
                                # Update global spatial distribution
                                if level_name not in result['spatial_distribution']:
                                    result['spatial_distribution'][level_name] = 0
                                result['spatial_distribution'][level_name] += 1
                        except:
                            continue
                    
                    # Add example elements (limited by max_examples_per_type)
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
        raise Exception(f"Error analyzing element types and distribution: {str(e)}")