import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union
from collections import Counter


def get_elements_by_type_with_properties(
    ifc_file,
    element_types: List[str],
    include_property_sets: bool = True,
    property_set_filter: Optional[List[str]] = None,
    include_basic_info: bool = True,
    name_keywords: Optional[List[str]] = None,
    object_type_keywords: Optional[List[str]] = None,
    case_sensitive: bool = False,
    include_summary: bool = False,
    summary_by_property: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves IFC elements of specified types and extracts their property sets and basic information.
    Enhanced with keyword-based filtering capabilities and optional summary statistics.
    
    This function handles the common pattern of getting specific element types (like 
    IfcUnitaryEquipment, IfcBoiler, IfcAirTerminal) along with their property data,
    answering questions like 'what unitary equipment systems are installed?' or 
    'what boilers are in the model?'. When include_summary=True, it also provides
    summary statistics similar to count_elements_by_type, eliminating the need for
    separate calls.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element type strings to retrieve 
                      (e.g., ['IfcUnitaryEquipment', 'IfcUnitaryEquipmentType'])
        include_property_sets: Boolean to include property set extraction (default: True)
        property_set_filter: Optional list of specific property set names to extract 
                            (default: all)
        include_basic_info: Boolean to include basic element info like Name, ObjectType, 
                           Description (default: True)
        name_keywords: Optional list of keywords to filter elements by Name field.
                      Elements must contain at least one of the keywords to be included.
        object_type_keywords: Optional list of keywords to filter elements by ObjectType field.
                             Elements must contain at least one of the keywords to be included.
        case_sensitive: Boolean controlling whether keyword matching is case sensitive 
                       (default: False)
        include_summary: Boolean to include summary statistics (default: False)
        summary_by_property: Optional property name to categorize elements by 
                           (e.g., 'ObjectType', 'PredefinedType', 'Name') (default: None)
    
    Returns:
        Dict containing:
        - elements_by_type: Dict mapping element types to lists of element details
        - total_elements: Total count of elements found
        - element_types_found: List of element types that had elements
        - filtered_elements: Count of elements that passed keyword filtering (only when keywords used)
        - summary: Dict with summary statistics (only when include_summary=True)
          - total_count: Total number of elements
          - type_counts: Dict mapping element types to counts
          - property_distribution: Dict mapping property values to counts (when summary_by_property specified)
    
    Example usage:
        import ifcopenshell
        model = ifcopenshell.open('model.ifc')
        
        # Original usage (backward compatible)
        result = get_elements_by_type_with_properties(
            model, 
            ['IfcUnitaryEquipment', 'IfcUnitaryEquipmentType']
        )
        
        # Enhanced usage with keyword filtering
        result = get_elements_by_type_with_properties(
            model,
            ['IfcBuildingElementProxy'],
            name_keywords=['Water Heater'],
            case_sensitive=False
        )
        
        # Enhanced usage with summary
        result = get_elements_by_type_with_properties(
            model,
            ['IfcRailing'],
            include_summary=True,
            summary_by_property='PredefinedType'
        )
        print(f"Found {result['summary']['total_count']} railings")
        print(f"By type: {result['summary']['type_counts']}")
        print(f"By predefined type: {result['summary']['property_distribution']}")
    """
    try:
        result = {
            'elements_by_type': {},
            'total_elements': 0,
            'element_types_found': []
        }
        
        # Add filtered_elements count only when keywords are used
        if name_keywords or object_type_keywords:
            result['filtered_elements'] = 0
        
        # Helper function for keyword matching
        def matches_keywords(text: str, keywords: List[str]) -> bool:
            if not text or not keywords:
                return False
            
            search_text = text if case_sensitive else text.lower()
            
            for keyword in keywords:
                search_keyword = keyword if case_sensitive else keyword.lower()
                if search_keyword in search_text:
                    return True
            return False
        
        # Data structures for summary
        summary_data = {
            'type_counts': {},
            'property_values': []
        } if include_summary else None
        
        for element_type in element_types:
            try:
                # Get all elements of this type
                elements = ifc_file.by_type(element_type)
                
                if not elements:
                    result['elements_by_type'][element_type] = []
                    if include_summary:
                        summary_data['type_counts'][element_type] = 0
                    continue
                    
                element_details = []
                
                for element in elements:
                    # Apply keyword filtering if specified
                    element_name = getattr(element, 'Name', None) or ''
                    element_object_type = getattr(element, 'ObjectType', None) or ''
                    
                    # Skip element if it doesn't match keyword criteria
                    if name_keywords and not matches_keywords(element_name, name_keywords):
                        continue
                    
                    if object_type_keywords and not matches_keywords(element_object_type, object_type_keywords):
                        continue
                    
                    element_info = {}
                    
                    # Include basic information if requested
                    if include_basic_info:
                        element_info['id'] = element.id()
                        element_info['name'] = element_name
                        element_info['object_type'] = element_object_type
                        element_info['description'] = getattr(element, 'Description', None)
                        element_info['global_id'] = getattr(element, 'GlobalId', None)
                        
                        # Add predefined type if available
                        if hasattr(element, 'PredefinedType'):
                            element_info['predefined_type'] = getattr(element, 'PredefinedType', None)
                    
                    # Include property sets if requested
                    if include_property_sets:
                        try:
                            # Use ifcopenshell.util.element.get_psets for property extraction
                            psets = ifcopenshell.util.element.get_psets(element)
                            
                            if property_set_filter:
                                # Filter to only requested property sets
                                filtered_psets = {}
                                for pset_name in property_set_filter:
                                    if pset_name in psets:
                                        filtered_psets[pset_name] = psets[pset_name]
                                element_info['property_sets'] = filtered_psets
                            else:
                                element_info['property_sets'] = psets
                                
                        except Exception as pset_error:
                            # Fallback to manual property extraction if util fails
                            element_info['property_sets'] = {}
                            try:
                                for rel in element.IsDefinedBy:
                                    if hasattr(rel, 'RelatingPropertyDefinition'):
                                        prop_def = rel.RelatingPropertyDefinition
                                        if hasattr(prop_def, 'HasProperties'):
                                            pset_name = getattr(prop_def, 'Name', 'Unknown')
                                            pset_data = {}
                                            for prop in prop_def.HasProperties:
                                                if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                                    prop_name = prop.Name
                                                    prop_value = prop.NominalValue.wrappedValue if hasattr(prop.NominalValue, 'wrappedValue') else prop.NominalValue
                                                    pset_data[prop_name] = prop_value
                                            
                                            # Apply filter if specified
                                            if not property_set_filter or pset_name in property_set_filter:
                                                element_info['property_sets'][pset_name] = pset_data
                            except Exception as fallback_error:
                                element_info['property_sets'] = {'error': str(fallback_error)}
                    
                    element_details.append(element_info)
                    
                    # Collect summary data
                    if include_summary:
                        # Collect property value for distribution if specified
                        if summary_by_property:
                            if summary_by_property.lower() == 'name':
                                prop_value = element_name
                            elif summary_by_property.lower() == 'objecttype':
                                prop_value = element_object_type
                            elif summary_by_property.lower() == 'predefinedtype':
                                prop_value = getattr(element, 'PredefinedType', None) or 'N/A'
                            else:
                                # Try to get from basic info first
                                prop_value = element_info.get(summary_by_property)
                                if prop_value is None:
                                    # Try to get from property sets
                                    if 'property_sets' in element_info:
                                        for pset in element_info['property_sets'].values():
                                            if isinstance(pset, dict) and summary_by_property in pset:
                                                prop_value = pset[summary_by_property]
                                                break
                                
                            if prop_value is None:
                                prop_value = 'N/A'
                            
                            summary_data['property_values'].append(str(prop_value))
                
                result['elements_by_type'][element_type] = element_details
                result['total_elements'] += len(elements)
                
                # Update filtered_elements count if keywords were used
                if name_keywords or object_type_keywords:
                    result['filtered_elements'] += len(element_details)
                
                # Update summary data
                if include_summary:
                    summary_data['type_counts'][element_type] = len(element_details)
                
                if element_details:  # Only add to found types if we have elements after filtering
                    result['element_types_found'].append(element_type)
                
            except Exception as type_error:
                result['elements_by_type'][element_type] = [{'error': f"Error processing type {element_type}: {str(type_error)}"}]
                if include_summary:
                    summary_data['type_counts'][element_type] = 0
        
        # Add summary to result if requested
        if include_summary:
            summary = {
                'total_count': result['filtered_elements'] if (name_keywords or object_type_keywords) else result['total_elements'],
                'type_counts': summary_data['type_counts']
            }
            
            # Add property distribution if summary_by_property was specified
            if summary_by_property and summary_data['property_values']:
                property_counts = Counter(summary_data['property_values'])
                summary['property_distribution'] = dict(property_counts)
            
            result['summary'] = summary
        
        return result
        
    except Exception as e:
        return {
            'elements_by_type': {},
            'total_elements': 0,
            'element_types_found': [],
            'error': f"General error in get_elements_by_type_with_properties: {str(e)}"
        }