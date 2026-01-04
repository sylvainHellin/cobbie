import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def search_system_components_by_keywords(
    ifc_file,
    system_keywords: List[str],
    element_types: Optional[List[str]] = None,
    case_sensitive: bool = False,
    search_fields: List[str] = ['Name', 'ObjectType'],
    include_system_info: bool = True,
    max_results: int = 100,
    group_by_type: bool = True
) -> Dict[str, Any]:
    """
    Searches for MEP system components across multiple element types using keyword matching.
    
    This function handles the common BIM challenge of finding system components 
    (heating, plumbing, electrical, fire protection, etc.) in models where elements 
    exist but aren't organized into formal IfcSystem or IfcDistributionSystem structures.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        system_keywords: List of keywords to identify system components 
                        (e.g., ['HEAT', 'HEATING', 'BOILER', 'RADIATOR'])
        element_types: List of IFC element types to search. Defaults to common MEP types if None.
        case_sensitive: Whether keyword matching should be case sensitive (default False)
        search_fields: List of element fields to search in (default ['Name', 'ObjectType'])
        include_system_info: Whether to check for formal system associations (default True)
        max_results: Maximum number of results to return (default 100)
        group_by_type: Whether to group results by element type (default True)
    
    Returns:
        Dict containing:
        - total_found: Total number of matching elements
        - elements_by_type: Dictionary grouping found elements by their IFC type
        - elements_with_systems: Elements that have formal system associations
        - formal_systems: List of IfcSystem/IfcDistributionSystem elements found
        - search_summary: Summary of search parameters and results
        
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = search_system_components_by_keywords(
        ...     model,
        ...     system_keywords=['HEAT', 'HEATING', 'BOILER', 'RADIATOR'],
        ...     case_sensitive=False
        ... )
        >>> print(f"Found {result['total_found']} heating components")
    """
    
    # Default MEP element types if none provided
    if element_types is None:
        element_types = [
            'IfcDistributionElement',
            'IfcDistributionControlElement',
            'IfcDistributionFlowElement',
            'IfcEnergyConversionDevice',
            'IfcFlowTerminal',
            'IfcFlowController',
            'IfcFlowMovingDevice',
            'IfcFlowStorageDevice'
        ]
    
    # Prepare keywords for matching
    if not case_sensitive:
        system_keywords = [keyword.upper() for keyword in system_keywords]
    
    found_elements = []
    elements_by_type = {}
    elements_with_systems = []
    
    # Search through each element type
    for element_type in element_types:
        try:
            elements = ifc_file.by_type(element_type)
            type_matches = []
            
            for element in elements:
                # Check each search field for keyword matches
                field_matches = []
                for field in search_fields:
                    try:
                        field_value = getattr(element, field, None)
                        if field_value:
                            search_value = field_value if case_sensitive else field_value.upper()
                            if any(keyword in search_value for keyword in system_keywords):
                                field_matches.append(field)
                    except AttributeError:
                        continue
                
                # If any field matches, add element to results
                if field_matches:
                    element_info = {
                        'GlobalId': element.GlobalId,
                        'Type': element_type,
                        'Name': element.Name,
                        'ObjectType': element.ObjectType,
                        'MatchedFields': field_matches
                    }
                    
                    # Check for system associations if requested
                    if include_system_info:
                        try:
                            # Get systems this element belongs to
                            systems = ifcopenshell.util.element.get_systems(element)
                            if systems:
                                element_info['Systems'] = [sys.Name or sys.GlobalId for sys in systems]
                                elements_with_systems.append(element_info)
                        except:
                            element_info['Systems'] = []
                    
                    found_elements.append(element_info)
                    type_matches.append(element_info)
            
            # Group by type if requested
            if group_by_type and type_matches:
                elements_by_type[element_type] = type_matches
                
        except Exception as e:
            # Continue with other element types if one fails
            continue
    
    # Limit results if specified
    if max_results and len(found_elements) > max_results:
        found_elements = found_elements[:max_results]
        if group_by_type:
            # Also limit grouped results
            total_in_groups = 0
            for element_type in elements_by_type:
                if total_in_groups >= max_results:
                    break
                remaining = max_results - total_in_groups
                elements_by_type[element_type] = elements_by_type[element_type][:remaining]
                total_in_groups += len(elements_by_type[element_type])
    
    # Find formal systems in the model
    formal_systems = []
    if include_system_info:
        try:
            # Check for IfcSystem elements
            systems = ifc_file.by_type('IfcSystem')
            for system in systems:
                formal_systems.append({
                    'GlobalId': system.GlobalId,
                    'Name': system.Name,
                    'ObjectType': system.ObjectType,
                    'Type': 'IfcSystem'
                })
        except:
            pass
        
        try:
            # Check for IfcDistributionSystem elements
            dist_systems = ifc_file.by_type('IfcDistributionSystem')
            for system in dist_systems:
                formal_systems.append({
                    'GlobalId': system.GlobalId,
                    'Name': system.Name,
                    'ObjectType': system.ObjectType,
                    'Type': 'IfcDistributionSystem'
                })
        except:
            pass
    
    # Create search summary
    search_summary = {
        'keywords_searched': system_keywords,
        'element_types_searched': element_types,
        'search_fields': search_fields,
        'case_sensitive': case_sensitive,
        'include_system_info': include_system_info,
        'max_results_limit': max_results
    }
    
    return {
        'total_found': len(found_elements),
        'elements_by_type': elements_by_type,
        'elements_with_systems': elements_with_systems,
        'formal_systems': formal_systems,
        'search_summary': search_summary
    }