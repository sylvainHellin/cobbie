import ifcopenshell
from typing import List, Dict, Any, Optional, Literal, Union


def find_elements_by_semantic_keywords(
    model: ifcopenshell.file,
    keywords: List[str],
    ifc_types: Optional[List[str]] = None,
    keyword_attributes: List[str] = ['Name'],
    case_sensitive: bool = False,
    match_mode: Literal['any', 'all'] = 'any',
    include_properties: bool = False,
    include_attributes: List[str] = ['Name', 'GlobalId', 'ObjectType']
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Searches for specific building elements across a list of candidate IFC types by
    matching keywords in their names or attributes.
    
    This function addresses the common BIM scenario where equipment is modeled using
    generic IFC types (like IfcFlowTerminal or IfcFlowController) but distinguished by
    specific naming conventions. It supports searching multiple types in one call to
    handle schema variations or differing modeling practices.
    
    Args:
        model: The loaded IFC model instance.
        keywords: List of keywords to search for in element attributes (e.g., ['panel', 'board']).
        ifc_types: List of IFC types to search within. If None, defaults to common MEP container
            types: ['IfcFlowTerminal', 'IfcFlowController', 'IfcDistributionControlElement',
            'IfcElectricDistributionPoint', 'IfcJunctionBox', 'IfcElectricAppliance'].
        keyword_attributes: The attributes to search for keywords (e.g., ['Name', 'ObjectType']).
            Defaults to ['Name'].
        case_sensitive: Whether the keyword match is case sensitive. Defaults to False.
        match_mode: Whether elements must match 'any' or 'all' keywords. Defaults to 'any'.
        include_properties: If True, returns full property details for matches.
            Defaults to False.
        include_attributes: List of attributes to include in the result
            (e.g., ['Name', 'GlobalId', 'ObjectType']). Defaults to ['Name', 'GlobalId', 'ObjectType'].
    
    Returns:
        A dictionary where keys are the IFC types searched and values are lists of matching
        elements. Each element is represented as a dictionary containing:
        - Requested attributes (e.g., 'Name', 'GlobalId', 'ObjectType')
        - 'Properties' dictionary (if include_properties=True)
        
        Example:
        {
            'IfcFlowTerminal': [
                {
                    'Name': 'Unit A Panelboard',
                    'GlobalId': '0dJKPQcDL7OOA9T2YsJr1q',
                    'ObjectType': '400 A',
                    'Properties': { ... }  # if include_properties=True
                }
            ],
            'IfcFlowController': []
        }
    
    Example Usage:
        >>> model = ifcopenshell.open('model.ifc')
        >>> panels = find_elements_by_semantic_keywords(
        ...     model,
        ...     keywords=['panel', 'board'],
        ...     ifc_types=['IfcFlowTerminal', 'IfcFlowController'],
        ...     include_properties=True
        ... )
        >>> print(f"Found {len(panels['IfcFlowTerminal'])} panels")
    
    Note:
        Elements missing requested attributes will be skipped. If an IFC type doesn't
        exist in the model schema, it will return an empty list for that type.
    """
    # Set default IFC types if not provided
    if ifc_types is None:
        ifc_types = [
            'IfcFlowTerminal',
            'IfcFlowController',
            'IfcDistributionControlElement',
            'IfcElectricDistributionPoint',
            'IfcJunctionBox',
            'IfcElectricAppliance'
        ]
    
    # Validate inputs
    if not keywords:
        return {ifc_type: [] for ifc_type in ifc_types}
    
    if not ifc_types:
        return {}
    
    if not keyword_attributes:
        keyword_attributes = ['Name']
    
    # Prepare keywords for matching
    if not case_sensitive:
        search_keywords = [kw.lower() for kw in keywords]
    else:
        search_keywords = keywords
    
    results: Dict[str, List[Dict[str, Any]]] = {}
    total_skipped = 0
    
    for ifc_type in ifc_types:
        results[ifc_type] = []
        
        try:
            # Get all elements of this type
            elements = list(model.by_type(ifc_type))
        except RuntimeError:
            # Type not found in schema, skip
            continue
        
        for element in elements:
            try:
                # Check for keyword matches in specified attributes
                matches = False
                match_count = 0
                
                for attr_name in keyword_attributes:
                    attr_value = getattr(element, attr_name, None)
                    if attr_value is None:
                        continue
                    
                    attr_str = str(attr_value)
                    search_str = attr_str if case_sensitive else attr_str.lower()
                    
                    for kw in search_keywords:
                        if kw in search_str:
                            if match_mode == 'any':
                                matches = True
                                break
                            elif match_mode == 'all':
                                match_count += 1
                    
                    if matches and match_mode == 'any':
                        break
                
                # For 'all' mode, check if all keywords were found
                if match_mode == 'all' and match_count >= len(search_keywords):
                    matches = True
                
                if matches:
                    # Build result element dictionary
                    elem_result: Dict[str, Any] = {}
                    
                    # Include requested attributes
                    for attr in include_attributes:
                        elem_result[attr] = getattr(element, attr, None)
                    
                    # Include properties if requested
                    if include_properties:
                        properties: Dict[str, Any] = {}
                        for definition in element.IsDefinedBy:
                            try:
                                if hasattr(definition, 'RelatingPropertyDefinition'):
                                    pdef = definition.RelatingPropertyDefinition
                                    if hasattr(pdef, 'HasProperties'):
                                        pset_name = getattr(pdef, 'Name', 'Unknown')
                                        if pset_name not in properties:
                                            properties[pset_name] = {}
                                        for prop in pdef.HasProperties:
                                            prop_name = getattr(prop, 'Name', 'Unknown')
                                            if hasattr(prop, 'NominalValue'):
                                                try:
                                                    properties[pset_name][prop_name] = prop.NominalValue.wrappedValue
                                                except (AttributeError, TypeError):
                                                    properties[pset_name][prop_name] = None
                            except (AttributeError, TypeError):
                                continue
                        elem_result['Properties'] = properties
                    
                    # Only add if it has a valid ID
                    if elem_result.get('GlobalId') is not None:
                        results[ifc_type].append(elem_result)
                    else:
                        total_skipped += 1
            
            except AttributeError:
                total_skipped += 1
                continue
    
    if total_skipped > 0:
        print(f"Warning: Skipped {total_skipped} elements due to missing attributes or errors")
    
    return results