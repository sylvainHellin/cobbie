import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def filter_elements_by_property_value(
    ifc_file,
    element_type: str,
    filter_property_set: str,
    filter_property_name: str,
    filter_property_value: Any,
    extract_property_sets: List[str],
    extract_property_names: List[str],
    include_basic_info: bool = True
) -> List[Dict[str, Any]]:
    """
    Filters IFC elements of a specified type by exact property values and extracts specified property values.
    This function is designed for common BIM queries like 'find all spaces on level X with their areas' 
    or 'get all doors with fire rating Y and their widths'.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSpace', 'IfcDoor', 'IfcWall')
        filter_property_set: Name of the property set to filter by (e.g., 'Pset_SpaceCustom')
        filter_property_name: Name of the property to filter by (e.g., 'Ebene')
        filter_property_value: Value to match for filtering (e.g., 'First Floor')
        extract_property_sets: List of property sets to extract values from (e.g., ['Pset_SpaceCustom'])
        extract_property_names: List of property names to extract (e.g., ['Area'])
        include_basic_info: Whether to include Name, LongName, ObjectType in results (default: True)
    
    Returns:
        List of dictionaries, each containing the matching element with requested property values.
        Each dict includes basic element info and the extracted property values.
    
    Example:
        # Find all spaces on First Floor with their areas
        results = filter_elements_by_property_value(
            ifc_file,
            'IfcSpace',
            'Pset_SpaceCustom',
            'Ebene',
            'First Floor',
            ['Pset_SpaceCustom'],
            ['Area']
        )
        
        # Get all doors with fire rating '2HR' and their widths
        results = filter_elements_by_property_value(
            ifc_file,
            'IfcDoor',
            'Pset_DoorCommon',
            'FireRating',
            '2HR',
            ['Pset_DoorCommon'],
            ['Width']
        )
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        filtered_results = []
        
        for element in elements:
            try:
                # Get all property sets for this element (includes inherited properties)
                element_psets = ifcopenshell.util.element.get_psets(element)
                actual_value = None
                property_source = None
                
                # Check if the filter property set exists and has the filter property on element
                if filter_property_set in element_psets:
                    filter_pset = element_psets[filter_property_set]
                    if filter_property_name in filter_pset:
                        actual_value = filter_pset[filter_property_name]
                        property_source = 'element'
                
                # If not found on element, check type object for inherited properties
                if actual_value is None:
                    type_object = ifcopenshell.util.element.get_type(element)
                    if type_object:
                        type_psets = ifcopenshell.util.element.get_psets(type_object)
                        if filter_property_set in type_psets:
                            filter_pset = type_psets[filter_property_set]
                            if filter_property_name in filter_pset:
                                actual_value = filter_pset[filter_property_name]
                                property_source = 'type'
                
                # Check if the filter property matches the desired value
                matches_filter = False
                if actual_value == filter_property_value:
                    matches_filter = True
                # Special handling for LoadBearing=False: treat undefined as False
                elif (filter_property_value is False and 
                      filter_property_name == 'LoadBearing' and 
                      actual_value is None):
                    matches_filter = True
                    actual_value = False
                    property_source = 'inferred'
                
                if matches_filter:
                    # Create result dictionary
                    result = {}
                    
                    # Include basic info if requested
                    if include_basic_info:
                        result['Name'] = getattr(element, 'Name', None)
                        result['LongName'] = getattr(element, 'LongName', None)
                        result['ObjectType'] = getattr(element, 'ObjectType', None)
                        result['GlobalId'] = getattr(element, 'GlobalId', None)
                    
                    # Extract requested properties (check element first, then type)
                    for pset_name in extract_property_sets:
                        # Get property set from element or type
                        if pset_name in element_psets:
                            pset = element_psets[pset_name]
                        else:
                            # Check type object
                            type_object = ifcopenshell.util.element.get_type(element)
                            if type_object:
                                type_psets = ifcopenshell.util.element.get_psets(type_object)
                                pset = type_psets.get(pset_name, {})
                            else:
                                pset = {}
                        
                        for prop_name in extract_property_names:
                            # Create a key that combines the property set and property name
                            # to avoid conflicts when extracting from multiple property sets
                            if len(extract_property_sets) > 1:
                                key = f"{pset_name}_{prop_name}"
                            else:
                                key = prop_name
                            result[key] = pset.get(prop_name)
                    
                    filtered_results.append(result)
                    
            except Exception as e:
                # Skip elements that cause errors and continue with others
                continue
        
        return filtered_results
        
    except Exception as e:
        # Return empty list if there's an overall error
        return []