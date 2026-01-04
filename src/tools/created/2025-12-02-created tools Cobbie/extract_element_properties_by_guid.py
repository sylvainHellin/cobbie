import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Union, Any

def extract_element_properties_by_guid(
    ifc_file,
    element_guid: str,
    property_sets_filter: Optional[List[str]] = None,
    properties_filter: Optional[List[str]] = None,
    include_basic_attributes: bool = True,
    include_empty_properties: bool = False,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Extracts comprehensive property information for a single IFC element identified by its GUID.
    This function handles the common BIM task of retrieving detailed element data including 
    all property sets, individual properties, and basic element attributes. It provides 
    structured output suitable for analysis, reporting, or validation workflows.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        element_guid: GUID of the element to analyze
        property_sets_filter: Optional list of property set names to prioritize (if None, includes all)
        properties_filter: Optional list of specific property names to extract (if None, includes all)
        include_basic_attributes: Whether to include Name, ObjectType, Type (default True)
        include_empty_properties: Whether to include properties with placeholder/default values (default False)
        case_sensitive: Whether property name matching is case sensitive (default False)
    
    Returns:
        Dict containing:
        - element_found: Boolean indicating if element was found
        - element_info: Basic element attributes (id, type, name, etc.)
        - property_sets: Dict of property sets with their properties
        - summary: Count of property sets and properties found
        - error_message: Error details if element not found
    
    Example:
        import ifcopenshell
        model = ifcopenshell.open('model.ifc')
        result = extract_element_properties_by_guid(
            model, 
            '0otfaO0qPDAhynjJ6DmgH8',
            property_sets_filter=['PSet_Revit_Type_Dimensions']
        )
        print(result['property_sets']['PSet_Revit_Type_Dimensions']['Height'])  # 1.735
    """
    
    result = {
        'element_found': False,
        'element_info': {},
        'property_sets': {},
        'summary': {'property_sets_count': 0, 'properties_count': 0},
        'error_message': None
    }
    
    try:
        # Try to find the element by GUID
        element = ifc_file.by_guid(element_guid)
        result['element_found'] = True
        
        # Extract basic element information
        if include_basic_attributes:
            result['element_info'] = {
                'id': element.id(),
                'guid': element.GlobalId,
                'type': element.is_a(),
                'name': getattr(element, 'Name', None),
                'object_type': getattr(element, 'ObjectType', None),
                'description': getattr(element, 'Description', None)
            }
        
        # Get all property sets using ifcopenshell.util.element.get_psets
        all_psets = ifcopenshell.util.element.get_psets(element)
        
        # Apply filters
        filtered_psets = {}
        total_properties = 0
        
        for pset_name, pset_data in all_psets.items():
            # Apply property set filter
            if property_sets_filter is not None:
                if case_sensitive:
                    if pset_name not in property_sets_filter:
                        continue
                else:
                    if pset_name.lower() not in [f.lower() for f in property_sets_filter]:
                        continue
            
            # Filter properties within the property set
            filtered_properties = {}
            for prop_name, prop_value in pset_data.items():
                # Skip if it's the 'id' field (internal)
                if prop_name == 'id':
                    continue
                
                # Apply property filter
                if properties_filter is not None:
                    if case_sensitive:
                        if prop_name not in properties_filter:
                            continue
                    else:
                        if prop_name.lower() not in [f.lower() for f in properties_filter]:
                            continue
                
                # Check for empty/placeholder values
                if not include_empty_properties:
                    if prop_value is None:
                        continue
                    if isinstance(prop_value, str):
                        # Check for common placeholder values
                        placeholders = ['', ' ', 'None', 'null', 'undefined', 'Unknown', 'N/A']
                        if prop_value.strip() in placeholders:
                            continue
                
                filtered_properties[prop_name] = prop_value
                total_properties += 1
            
            # Only include property set if it has properties after filtering
            if filtered_properties:
                filtered_psets[pset_name] = filtered_properties
        
        result['property_sets'] = filtered_psets
        result['summary'] = {
            'property_sets_count': len(filtered_psets),
            'properties_count': total_properties
        }
        
    except RuntimeError as e:
        result['error_message'] = f"Element with GUID '{element_guid}' not found: {str(e)}"
    except Exception as e:
        result['error_message'] = f"Error processing element: {str(e)}"
    
    return result