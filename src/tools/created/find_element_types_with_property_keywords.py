import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union
import json

def find_element_types_with_property_keywords(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    property_keywords: List[str],
    search_instances: bool = True,
    search_types: bool = True,
    categorize_by: str = 'ObjectType',
    case_sensitive: bool = False,
    include_property_details: bool = True,
    max_examples_per_type: int = 3
) -> Dict[str, Any]:
    """
    Finds element types that contain properties matching specific keywords.
    
    This function systematically searches through property sets of both element 
    instances and type objects to identify which element types contain target 
    properties (e.g., fire rating, accessibility, energy performance).
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element types to analyze (e.g., ['IfcDoor', 'IfcWall', 'IfcWindow'])
        property_keywords: List of keywords to search for in property names (e.g., ['fire', 'rating', 'resistance'])
        search_instances: Boolean to search element instances (default: True)
        search_types: Boolean to search element type objects (default: True)
        categorize_by: Field to categorize elements by (default: 'ObjectType', options: 'Name', 'PredefinedType')
        case_sensitive: Boolean for case-sensitive keyword matching (default: False)
        include_property_details: Boolean to include specific property names and values (default: True)
        max_examples_per_type: Maximum number of examples to show per element type (default: 3)
    
    Returns:
        Dict containing:
        - 'element_types_with_properties': List of element types that contain matching properties
        - 'element_types_without_properties': List of element types that don't contain matching properties
        - 'property_details': Dict mapping element types to their matching properties
        - 'summary': Total counts and statistics
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = find_element_types_with_property_keywords(
        ...     model, 
        ...     ['IfcDoor'], 
        ...     ['fire', 'rating', 'resistance']
        ... )
        >>> print(result['element_types_with_properties'])
    """
    
    try:
        # Initialize result structure
        result = {
            'element_types_with_properties': [],
            'element_types_without_properties': [],
            'property_details': {},
            'summary': {
                'total_element_types_searched': 0,
                'total_elements_analyzed': 0,
                'total_property_sets_analyzed': 0,
                'total_matching_properties_found': 0
            }
        }
        
        # Validate categorize_by parameter
        valid_categorize_fields = ['ObjectType', 'Name', 'PredefinedType']
        if categorize_by not in valid_categorize_fields:
            categorize_by = 'ObjectType'
        
        # Prepare keywords for matching
        if not case_sensitive:
            search_keywords = [kw.lower() for kw in property_keywords]
        else:
            search_keywords = property_keywords
        
        # Track all element types found and those with properties
        all_element_types = set()
        element_types_with_props = set()
        examples_count_per_type = {}
        
        # Process each element type
        for element_type in element_types:
            try:
                # Get element instances
                instances = ifc_file.by_type(element_type)
                result['summary']['total_elements_analyzed'] += len(instances)
                
                # Get element type objects
                type_objects = ifc_file.by_type(element_type + 'Type')
                
                # Search instances if requested
                if search_instances:
                    for instance in instances:
                        try:
                            # Get categorization value
                            category_value = getattr(instance, categorize_by, None)
                            if category_value is None:
                                category_value = 'Unknown'
                            elif hasattr(category_value, 'wrappedValue'):
                                category_value = category_value.wrappedValue
                            
                            category_str = str(category_value)
                            all_element_types.add(category_str)
                            
                            # Get property sets using utility function
                            psets = ifcopenshell.util.element.get_psets(instance)
                            result['summary']['total_property_sets_analyzed'] += len(psets)
                            
                            # Search for matching properties
                            found_matching_property = False
                            for pset_name, properties in psets.items():
                                for prop_name, prop_value in properties.items():
                                    # Check if property name contains any keywords
                                    search_name = prop_name if case_sensitive else prop_name.lower()
                                    
                                    if any(keyword in search_name for keyword in search_keywords):
                                        found_matching_property = True
                                        element_types_with_props.add(category_str)
                                        result['summary']['total_matching_properties_found'] += 1
                                        
                                        # Add property details if requested
                                        if include_property_details:
                                            if category_str not in result['property_details']:
                                                result['property_details'][category_str] = []
                                            
                                            # Check example limit for this type
                                            if category_str not in examples_count_per_type:
                                                examples_count_per_type[category_str] = 0
                                            
                                            if examples_count_per_type[category_str] < max_examples_per_type:
                                                result['property_details'][category_str].append({
                                                    'property_set': pset_name,
                                                    'property_name': prop_name,
                                                    'property_value': str(prop_value),
                                                    'element_id': instance.id(),
                                                    'element_type': 'instance'
                                                })
                                                examples_count_per_type[category_str] += 1
                            
                            # Ensure category is in property_details if it has matching properties
                            if found_matching_property and category_str not in result['property_details']:
                                result['property_details'][category_str] = []
                        
                        except Exception as e:
                            continue  # Skip problematic instances
                
                # Search type objects if requested
                if search_types:
                    for type_obj in type_objects:
                        try:
                            # Get categorization value
                            category_value = getattr(type_obj, categorize_by, None)
                            if category_value is None:
                                category_value = 'Unknown'
                            elif hasattr(category_value, 'wrappedValue'):
                                category_value = category_value.wrappedValue
                            
                            category_str = str(category_value)
                            all_element_types.add(category_str)
                            
                            # Get property sets using utility function
                            psets = ifcopenshell.util.element.get_psets(type_obj)
                            result['summary']['total_property_sets_analyzed'] += len(psets)
                            
                            # Search for matching properties
                            found_matching_property = False
                            for pset_name, properties in psets.items():
                                for prop_name, prop_value in properties.items():
                                    # Check if property name contains any keywords
                                    search_name = prop_name if case_sensitive else prop_name.lower()
                                    
                                    if any(keyword in search_name for keyword in search_keywords):
                                        found_matching_property = True
                                        element_types_with_props.add(category_str)
                                        result['summary']['total_matching_properties_found'] += 1
                                        
                                        # Add property details if requested
                                        if include_property_details:
                                            if category_str not in result['property_details']:
                                                result['property_details'][category_str] = []
                                            
                                            # Check example limit for this type
                                            if category_str not in examples_count_per_type:
                                                examples_count_per_type[category_str] = 0
                                            
                                            if examples_count_per_type[category_str] < max_examples_per_type:
                                                result['property_details'][category_str].append({
                                                    'property_set': pset_name,
                                                    'property_name': prop_name,
                                                    'property_value': str(prop_value),
                                                    'element_id': type_obj.id(),
                                                    'element_type': 'type_object'
                                                })
                                                examples_count_per_type[category_str] += 1
                            
                            # Ensure category is in property_details if it has matching properties
                            if found_matching_property and category_str not in result['property_details']:
                                result['property_details'][category_str] = []
                        
                        except Exception as e:
                            continue  # Skip problematic type objects
                
                result['summary']['total_element_types_searched'] += 1
            
            except Exception as e:
                continue  # Skip problematic element types
        
        # Compile final results
        result['element_types_with_properties'] = sorted(list(element_types_with_props))
        result['element_types_without_properties'] = sorted(list(all_element_types - element_types_with_props))
        
        return result
    
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'element_types_with_properties': [],
            'element_types_without_properties': [],
            'property_details': {},
            'summary': {
                'total_element_types_searched': 0,
                'total_elements_analyzed': 0,
                'total_property_sets_analyzed': 0,
                'total_matching_properties_found': 0
            }
        }