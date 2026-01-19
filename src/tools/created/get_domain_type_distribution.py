import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Callable, Optional, Union

# Domain mappings for auto-population of element_types
DOMAIN_TYPE_MAPS = {
    'mep': [
        'IfcDistributionElement',
        'IfcDistributionPort',
        'IfcDistributionFlowElement',
        'IfcDistributionControlElement',
        'IfcFlowTerminal',
        'IfcFlowController',
        'IfcFlowFitting',
        'IfcFlowMovingDevice',
        'IfcFlowSegment',
        'IfcFlowStorageDevice',
        'IfcPipeSegment',
        'IfcPipeFitting',
        'IfcSanitaryTerminal',
        'IfcValve',
        'IfcUnitaryEquipment',
        'IfcWasteTerminal',
        'IfcFlowMeter',
        'IfcFilter',
        'IfcCableSegment',
        'IfcCableFitting',
        'IfcJunctionBox',
        'IfcLamp',
        'IfcLightFixture',
        'IfcAirTerminal',
        'IfcAirTerminalBox',
        'IfcDuctSegment',
        'IfcDuctFitting'
    ],
    'structural': [
        'IfcStructuralMember',
        'IfcStructuralItem',
        'IfcStructuralCurveMember',
        'IfcStructuralSurfaceMember',
        'IfcColumn',
        'IfcBeam',
        'IfcFooting',
        'IfcPile',
        'IfcSlab',
        'IfcWall',
        'IfcWallStandardCase'
    ],
    'architectural': [
        'IfcBuildingElement',
        'IfcDoor',
        'IfcWindow',
        'IfcStair',
        'IfcStairFlight',
        'IfcRailing',
        'IfcRoof',
        'IfcCovering',
        'IfcFurnishingElement',
        'IfcFurniture',
        'IfcPlate',
        'IfcMember'
    ]
}

def get_domain_type_distribution(
    model: ifcopenshell.file,
    element_types: Optional[List[str]] = None,
    group_by_type_attribute: str = 'Name',
    include_percentages: bool = True,
    sort_by: Optional[str] = 'count',
    sort_order: str = 'desc',
    include_total: bool = True,
    filter_func: Optional[Callable[[Any], bool]] = None,
    empty_label: str = 'No Type',
    domains: Optional[List[str]] = None
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Analyzes and aggregates TypeObject-based distributions for multiple IFC types representing a building domain or system.
    
    This function iterates through specified IFC types, groups elements by their TypeObject's attribute,
    calculates counts and optional percentages, and returns a structured distribution analysis.
    
    Args:
        model: The loaded IFC model instance
        element_types: List of IFC class names to analyze (e.g., ['IfcPipeSegment', 'IfcPipeFitting'])
        group_by_type_attribute: Attribute on TypeObject to group by (default: 'Name')
        include_percentages: Whether to calculate percentage distribution within each IFC type (default: True)
        sort_by: Sort method for distributions - 'count', 'name', or None (default: 'count')
        sort_order: Sort direction - 'asc' or 'desc' (default: 'desc')
        include_total: Whether to include total count per IFC type (default: True)
        filter_func: Optional callable to filter elements before distribution
        empty_label: Label for elements without a TypeObject (default: 'No Type')
        domains: Optional domain names ('mep', 'structural', 'architectural') to auto-populate element_types.
                When provided, element_types will be automatically populated from the domain mappings.
    
    Returns:
        Nested dictionary where:
        - Outer key: IFC type name (e.g., 'IfcPipeSegment')
        - Middle key: TypeObject value (e.g., 'Rohrtypen:Edelstahl')
        - Inner dict: Contains 'count', 'percentage' (optional), and optional element details
        
    Example:
        >>> model = ifcopenshell.open('plumbing.ifc')
        >>> result = get_domain_type_distribution(
        ...     model,
        ...     element_types=['IfcPipeSegment', 'IfcPipeFitting'],
        ...     group_by_type_attribute='Name',
        ...     include_percentages=True
        ... )
        >>> print(result['IfcPipeSegment'])
        {'Rohrtypen:Edelstahl': {'count': 294, 'percentage': 58.33}, 
         'Rohrtypen:Abwasser HT': {'count': 208, 'percentage': 41.27},
         '_total': 504}
    """
    # Handle domains parameter to auto-populate element_types
    if domains:
        auto_types = set()
        for domain in domains:
            domain_lower = domain.lower()
            if domain_lower in DOMAIN_TYPE_MAPS:
                auto_types.update(DOMAIN_TYPE_MAPS[domain_lower])
        if element_types is None:
            element_types = list(auto_types)
        else:
            # Merge domains with provided element_types
            element_types = list(set(element_types) | auto_types)
    
    # Validate inputs
    if not element_types:
        return {}
    
    if model is None:
        raise ValueError("Model cannot be None")
    
    # Validate sort_by and sort_order
    if sort_by is not None and sort_by not in ['count', 'name']:
        raise ValueError(f"sort_by must be 'count', 'name', or None, got '{sort_by}'")
    
    if sort_order not in ['asc', 'desc']:
        raise ValueError(f"sort_order must be 'asc' or 'desc', got '{sort_order}'")
    
    result: Dict[str, Dict[str, Dict[str, Any]]] = {}
    
    for ifc_type in element_types:
        # Get all elements of this type
        try:
            elements = model.by_type(ifc_type)
        except Exception:
            # If type doesn't exist in model, skip it silently
            continue
        
        # Apply filter function if provided
        if filter_func is not None:
            elements = [elem for elem in elements if filter_func(elem)]
        
        if not elements:
            continue
        
        # Initialize distribution dictionary for this IFC type
        type_distribution: Dict[str, Dict[str, Any]] = {}
        type_skipped = 0
        
        for element in elements:
            try:
                # Get the TypeObject for this element
                type_obj = ifcopenshell.util.element.get_type(element)
                
                if type_obj is None:
                    group_key = empty_label
                else:
                    # Get the grouping attribute from the TypeObject
                    group_key = getattr(type_obj, group_by_type_attribute, None)
                    
                    if group_key is None:
                        group_key = empty_label
                    
                    # Ensure group_key is a string for dictionary key consistency
                    if not isinstance(group_key, str):
                        group_key = str(group_key)
                
                # Initialize entry if not exists
                if group_key not in type_distribution:
                    type_distribution[group_key] = {'count': 0}
                
                # Increment count
                type_distribution[group_key]['count'] += 1
                
            except (AttributeError, RuntimeError):
                # Skip elements that cause errors during processing
                type_skipped += 1
                continue
        
        # Calculate percentages if requested
        if include_percentages and type_distribution:
            total_count = sum(item['count'] for item in type_distribution.values())
            if total_count > 0:
                for key, item in type_distribution.items():
                    item['percentage'] = round((item['count'] / total_count) * 100, 2)
        
        # Add total if requested
        if include_total:
            total_count = sum(item['count'] for item in type_distribution.values())
            type_distribution['_total'] = {'count': total_count}
            if include_percentages and total_count > 0:
                type_distribution['_total']['percentage'] = 100.0
        
        # Sort the distribution
        if sort_by and sort_by in ['count', 'name']:
            reverse = (sort_order.lower() == 'desc')
            
            # Create a sorted list of (key, value) pairs, excluding '_total' from sorting
            items_to_sort = [(k, v) for k, v in type_distribution.items() if k != '_total']
            
            if sort_by == 'count':
                sorted_items = sorted(items_to_sort, key=lambda x: x[1]['count'], reverse=reverse)
            elif sort_by == 'name':
                sorted_items = sorted(items_to_sort, key=lambda x: x[0], reverse=reverse)
            
            # Rebuild dictionary with sorted order
            sorted_distribution: Dict[str, Dict[str, Any]] = {}
            for key, value in sorted_items:
                sorted_distribution[key] = value
            
            # Add back the _total entry at the end
            if '_total' in type_distribution:
                sorted_distribution['_total'] = type_distribution['_total']
            
            type_distribution = sorted_distribution
        
        # Store results if we have data
        if type_distribution:
            result[ifc_type] = type_distribution
    
    return result