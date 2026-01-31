import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Literal, Union

def summarize_elements_by_type(
    model: ifcopenshell.file,
    ifc_type: str,
    attributes: Optional[List[str]] = None,
    properties: Optional[List[str]] = None,
    quantities: Optional[List[str]] = None,
    pset_name: str = 'PSet_Draughting',
    max_results: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: Literal['asc', 'desc'] = 'asc',
    # Existing Parameters
    filter_keywords: Optional[List[str]] = None,
    keyword_attributes: Optional[List[str]] = None,
    match_mode: Literal['any', 'all'] = 'any',
    # New Parameters
    name_filter: Optional[Union[str, List[str]]] = None,
    name_match_mode: Literal['exact', 'contains', 'startswith', 'endswith'] = 'contains',
    case_sensitive: bool = False,
    # Type Object Resolution Parameter
    resolve_type_object: bool = False
) -> List[Dict[str, Any]]:
    """
    Generates a summary list of elements for a specific IFC type, including key identifying 
    attributes, optionally extracted property values, element quantities, semantic keyword/name filtering,
    and TypeObject resolution.

    This function is designed for exploratory analysis when you need to review instances of a 
    class to identify which ones represent specific semantic concepts based on their names, 
    properties, or geometric quantities.

    Args:
        model: The loaded IFC model instance.
        ifc_type: The IFC class name to summarize (e.g., 'IfcBuildingElementProxy', 'IfcSpace').
        attributes: List of direct element attributes to extract for each instance.
                   If None, defaults to ['Name', 'GlobalId', 'ObjectType', 'PredefinedType'].
        properties: List of property names to extract from the specified property set.
                    If None or empty, no properties are extracted.
        quantities: List of quantity names to extract from IfcElementQuantity relationships 
                    (e.g., 'NetVolume', 'NetFootprintArea', 'Length'). 
                    If None or empty, no quantities are extracted.
        pset_name: The specific property set name to query for properties. Defaults to 'PSet_Draughting'.
        max_results: Maximum number of elements to return (pre-filter). Use None for no limit (default).
        sort_by: Optional key (attribute, property, or quantity name) to sort the results by.
                 If None, no sorting is applied. Defaults to None.
        sort_order: Sort order, either 'asc' for ascending or 'desc' for descending.
                    Only applies when sort_by is provided. Defaults to 'asc'.
        filter_keywords: Optional list of string keywords to filter elements by. If provided, 
                         only elements where at least one keyword is found in the specified 
                         attributes will be returned. Case-insensitive.
        keyword_attributes: List of attributes to check for keyword matches. 
                            Defaults to ['Name', 'LongName'] if filter_keywords is provided 
                            and this is None. These attributes are automatically added to the
                            extraction list if not already present.
        match_mode: If 'any', returns elements matching any keyword. If 'all', requires all 
                    keywords to be present. Defaults to 'any'.
        name_filter: A string or list of strings to search for specifically in the 'Name' attribute.
                      If provided, this acts as a primary filter on the element Name. 
                      Defaults to None (no filter).
        name_match_mode: How to match the name_filter. Options: 'exact', 'contains', 
                          'startswith', 'endswith'. Defaults to 'contains'.
        case_sensitive: Whether the name search should be case-sensitive. Defaults to False.
        resolve_type_object: If True, resolves the TypeObject for each element and adds
                             'TypeObject.Name', 'TypeObject.PredefinedType', 
                             'TypeObject.ElementType', and 'TypeObject.GlobalId' to the result.
                             Defaults to False.

    Returns:
        A list of dictionaries, where each dictionary represents an element instance
        containing the requested attributes, properties, quantities, and optionally TypeObject info.
        Returns an empty list if the IFC type is not found in the model schema.

    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> # Find railings and their types
        >>> railings = summarize_elements_by_type(
        ...     model,
        ...     'IfcRailing',
        ...     resolve_type_object=True
        ... )
    """
    # Set defaults
    if attributes is None:
        attributes = ['Name', 'GlobalId', 'ObjectType', 'PredefinedType']
    if properties is None:
        properties = []
    if quantities is None:
        quantities = []

    # If generic keyword filtering is enabled, ensure keyword attributes are extracted
    if filter_keywords:
        if keyword_attributes is None:
            keyword_attributes = ['Name', 'LongName']
        
        # Auto-add any missing keyword attributes to the extraction list
        attrs_set = set(attributes)
        for ka in keyword_attributes:
            if ka not in attrs_set:
                attributes.append(ka)
                attrs_set.add(ka)

    # Validate inputs
    if not isinstance(model, ifcopenshell.file):
        raise TypeError("model must be an ifcopenshell.file instance")
    if not isinstance(ifc_type, str):
        raise TypeError("ifc_type must be a string")
    if not isinstance(attributes, list):
        raise TypeError("attributes must be a list")
    if not isinstance(properties, list):
        raise TypeError("properties must be a list")
    if not isinstance(quantities, list):
        raise TypeError("quantities must be a list")
    if sort_order not in ('asc', 'desc'):
        raise ValueError("sort_order must be either 'asc' or 'desc'")
    if match_mode not in ('any', 'all'):
        raise ValueError("match_mode must be either 'any' or 'all'")
    if name_match_mode not in ('exact', 'contains', 'startswith', 'endswith'):
        raise ValueError("name_match_mode must be 'exact', 'contains', 'startswith', or 'endswith'")

    # Get elements of the specified type
    try:
        elements = model.by_type(ifc_type)
    except RuntimeError:
        # Type not found in schema - return empty list
        return []

    # Handle empty results
    if not elements:
        return []

    # Apply max_results limit if specified
    if max_results is not None:
        elements = elements[:max_results]

    results: List[Dict[str, Any]] = []
    property_errors = 0

    for elem in elements:
        elem_summary: Dict[str, Any] = {}
        
        # Extract direct attributes
        for attr in attributes:
            value = getattr(elem, attr, None)
            elem_summary[attr] = value

        # Resolve TypeObject if requested
        if resolve_type_object:
            try:
                type_obj = ifcopenshell.util.element.get_type(elem)
                if type_obj:
                    elem_summary['TypeObject.Name'] = getattr(type_obj, 'Name', None)
                    elem_summary['TypeObject.PredefinedType'] = getattr(type_obj, 'PredefinedType', None)
                    elem_summary['TypeObject.ElementType'] = getattr(type_obj, 'ElementType', None)
                    elem_summary['TypeObject.GlobalId'] = getattr(type_obj, 'GlobalId', None)
                else:
                    elem_summary['TypeObject.Name'] = None
                    elem_summary['TypeObject.PredefinedType'] = None
                    elem_summary['TypeObject.ElementType'] = None
                    elem_summary['TypeObject.GlobalId'] = None
            except RuntimeError:
                # Handle errors during type resolution gracefully
                elem_summary['TypeObject.Name'] = None
                elem_summary['TypeObject.PredefinedType'] = None
                elem_summary['TypeObject.ElementType'] = None
                elem_summary['TypeObject.GlobalId'] = None

        # Extract properties if requested
        if properties:
            try:
                # Get all property sets for the element
                psets = ifcopenshell.util.element.get_psets(elem, psets_only=True)
                
                # Check if the requested pset exists
                if pset_name in psets:
                    pset = psets[pset_name]
                    for prop_name in properties:
                        if prop_name in pset:
                            elem_summary[prop_name] = psets[pset_name][prop_name]
            except (RuntimeError, AttributeError):
                # Error accessing property sets - continue with attributes only
                property_errors += 1
                pass

        # Extract quantities if requested
        if quantities:
            for rel in elem.IsDefinedBy:
                if hasattr(rel, 'RelatingPropertyDefinition'):
                    prop_def = rel.RelatingPropertyDefinition
                    if prop_def.is_a('IfcElementQuantity'):
                        for quant in prop_def.Quantities:
                            q_name = quant.Name
                            if q_name in quantities:
                                # Determine the value attribute based on the quantity type
                                value = None
                                try:
                                    if hasattr(quant, 'VolumeValue'):
                                        value = float(quant.VolumeValue)
                                    elif hasattr(quant, 'AreaValue'):
                                        value = float(quant.AreaValue)
                                    elif hasattr(quant, 'LengthValue'):
                                        value = float(quant.LengthValue)
                                    elif hasattr(quant, 'CountValue'):
                                        value = float(quant.CountValue)
                                    elif hasattr(quant, 'WeightValue'):
                                        value = float(quant.WeightValue)
                                    elif hasattr(quant, 'TimeValue'):
                                        value = float(quant.TimeValue)
                                except (ValueError, TypeError):
                                    pass
                                
                                if value is not None:
                                    elem_summary[q_name] = value

        results.append(elem_summary)

    # Report if there were issues accessing properties
    if property_errors > 0:
        print(f"Warning: Could not access properties for {property_errors} elements")

    # Apply Specific Name Filtering
    if name_filter:
        if isinstance(name_filter, str):
            filters = [name_filter]
        else:
            filters = name_filter
            
        # Normalize filters for case sensitivity
        filters_to_check = filters
        if not case_sensitive:
            filters_to_check = [f.lower() for f in filters]
            
        filtered_results = []
        for item in results:
            elem_name = item.get('Name')
            if elem_name is None:
                continue
            
            # Prepare element name for comparison
            compare_name = str(elem_name)
            if not case_sensitive:
                compare_name = compare_name.lower()
            
            # Perform matching
            matches = False
            for f in filters_to_check:
                if name_match_mode == 'exact':
                    if compare_name == f:
                        matches = True
                        break
                elif name_match_mode == 'contains':
                    if f in compare_name:
                        matches = True
                        break
                elif name_match_mode == 'startswith':
                    if compare_name.startswith(f):
                        matches = True
                        break
                elif name_match_mode == 'endswith':
                    if compare_name.endswith(f):
                        matches = True
                        break
            
            if matches:
                filtered_results.append(item)
        
        results = filtered_results

    # Apply Generic Keyword Filtering
    if filter_keywords:
        search_attrs = keyword_attributes
        lower_keywords = [kw.lower() for kw in filter_keywords]
        
        filtered_results = []
        for item in results:
            search_strings = []
            for attr in search_attrs:
                val = item.get(attr)
                if val is not None:
                    search_strings.append(str(val))
            
            searchable_text = " ".join(search_strings).lower()
            
            is_match = False
            if match_mode == 'any':
                is_match = any(kw in searchable_text for kw in lower_keywords)
            elif match_mode == 'all':
                is_match = all(kw in searchable_text for kw in lower_keywords)
            
            if is_match:
                filtered_results.append(item)
        
        results = filtered_results

    # Apply sorting if requested (applied after filtering to sort the final list)
    if sort_by is not None:
        def sort_key(item: Dict[str, Any]) -> tuple:
            """Generate a sort key that handles missing values appropriately."""
            value = item.get(sort_by)
            has_value = sort_by in item and item[sort_by] is not None
            
            if not has_value:
                return (False, )
            else:
                return (True, value)
        
        try:
            results.sort(key=sort_key, reverse=(sort_order == 'desc'))
        except TypeError:
            def safe_sort_key(item: Dict[str, Any]) -> tuple:
                has_value = sort_by in item and item[sort_by] is not None
                if not has_value:
                    return (False, '')
                value = item[sort_by]
                try:
                    return (True, value)
                except TypeError:
                    return (True, str(value))
            
            results.sort(key=safe_sort_key, reverse=(sort_order == 'desc'))

    return results