import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Set, Optional, Union


def search_technical_properties_comprehensive(
    ifc_file: ifcopenshell.file,
    property_keywords: List[str],
    element_types: Optional[List[str]] = None,
    property_sets: Optional[List[str]] = None,
    component_keywords: Optional[List[str]] = None,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Comprehensively searches for technical properties (voltage, pressure, flow rate, etc.) 
    across multiple element types, property sets, and property names using intelligent fallback strategies.
    
    This function answers questions like 'what are the voltage levels used in the electrical system?' 
    or 'what are the pressure ratings in the plumbing system?' by systematically exploring where 
    technical specifications might be stored in the BIM model.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        property_keywords: List of keywords for the target property (e.g., ['voltage', 'spannung', 'volt'])
        element_types: Optional list of element types to search (default: common MEP types)
        property_sets: Optional list of property set names to check (default: common technical property sets)
        component_keywords: Optional keywords to identify relevant components (e.g., ['electric', 'electrical'])
        include_details: Whether to return detailed property information (default: True)
    
    Returns:
        Dict[str, Any] containing:
        - found_values: Set of unique property values found
        - property_details: List of detailed information about where each value was found
        - search_summary: Summary of search strategies attempted and results
        - components_analyzed: Information about components that were examined
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = search_technical_properties_comprehensive(
        ...     model,
        ...     property_keywords=['voltage', 'spannung', 'volt'],
        ...     component_keywords=['electric', 'electrical', 'ladestation']
        ... )
        >>> print(result['found_values'])
    """
    # Default element types to search
    if element_types is None:
        element_types = [
            'IfcBuildingElementProxy',
            'IfcFlowTerminal', 
            'IfcFlowController', 
            'IfcFlowStorageDevice',
            'IfcDistributionElement',
            'IfcDistributionControlElement',
            'IfcDistributionFlowElement',
            'IfcElectricDistributionPoint',
            'IfcElectricFlowStorageDevice',
            'IfcElectricGenerator',
            'IfcElectricMotor',
            'IfcElectricTimeControl'
        ]
    
    # Default property sets to check
    if property_sets is None:
        property_sets = [
            'Pset_ElectricalDeviceCommon',
            'Pset_ElectricDistributionPoint', 
            'Pset_ElectricalCircuit',
            'Pset_PipeFittingTypeCommon',
            'Pset_PipeSegmentTypeCommon',
            'Pset_PumpTypeCommon',
            'Pset_ValveTypeCommon',
            'Pset_FlowMeterTypeCommon',
            'Pset_Common',
            'Pset_BuildingElementProxyCommon',
            'Elektrik',
            'Electrical',
            'Technical'
        ]
    
    # Initialize results
    found_values: Set[str] = set()
    property_details: List[Dict[str, Any]] = []
    components_analyzed: List[Dict[str, Any]] = []
    search_summary: Dict[str, Any] = {
        'strategies_attempted': 0,
        'elements_checked': 0,
        'property_sets_checked': 0,
        'matches_found': 0
    }
    
    # Normalize keywords for case-insensitive comparison
    property_keywords_lower = [kw.lower() for kw in property_keywords]
    component_keywords_lower = [kw.lower() for kw in component_keywords] if component_keywords else []
    
    # Strategy 1: Search by element types and filter by component keywords
    search_summary['strategies_attempted'] += 1
    
    for element_type in element_types:
        try:
            elements = ifc_file.by_type(element_type)
            search_summary['elements_checked'] += len(elements)
            
            for element in elements:
                # Check if element matches component keywords
                element_matches = True
                if component_keywords_lower:
                    element_matches = (
                        (element.Name and any(kw in element.Name.lower() for kw in component_keywords_lower)) or
                        (element.ObjectType and any(kw in element.ObjectType.lower() for kw in component_keywords_lower))
                    )
                
                if element_matches:
                    # Record component analysis
                    component_info = {
                        'id': element.id(),
                        'type': element.is_a(),
                        'name': element.Name,
                        'object_type': element.ObjectType
                    }
                    components_analyzed.append(component_info)
                    
                    # Get property sets using utility function
                    try:
                        psets = ifcopenshell.util.element.get_psets(element)
                        search_summary['property_sets_checked'] += len(psets)
                        
                        for pset_name, pset_data in psets.items():
                            for prop_name, prop_value in pset_data.items():
                                # Check if property name matches keywords
                                if any(kw in prop_name.lower() for kw in property_keywords_lower):
                                    value_str = str(prop_value)
                                    found_values.add(value_str)
                                    
                                    if include_details:
                                        detail = {
                                            'element_id': element.id(),
                                            'element_name': element.Name,
                                            'element_type': element.is_a(),
                                            'property_set': pset_name,
                                            'property_name': prop_name,
                                            'property_value': prop_value,
                                            'search_strategy': 'element_type_filter'
                                        }
                                        property_details.append(detail)
                                        search_summary['matches_found'] += 1
                    
                    except Exception as e:
                        # Fallback to manual property access
                        try:
                            for definition in element.IsDefinedBy:
                                if hasattr(definition, 'RelatingPropertyDefinition'):
                                    pset = definition.RelatingPropertyDefinition
                                    if hasattr(pset, 'Name') and hasattr(pset, 'HasProperties'):
                                        pset_data = {}
                                        for prop in pset.HasProperties:
                                            if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                                prop_name = prop.Name
                                                prop_value = prop.NominalValue.wrappedValue
                                                
                                                if any(kw in prop_name.lower() for kw in property_keywords_lower):
                                                    value_str = str(prop_value)
                                                    found_values.add(value_str)
                                                    
                                                    if include_details:
                                                        detail = {
                                                            'element_id': element.id(),
                                                            'element_name': element.Name,
                                                            'element_type': element.is_a(),
                                                            'property_set': pset.Name,
                                                            'property_name': prop_name,
                                                            'property_value': prop_value,
                                                            'search_strategy': 'element_type_fallback'
                                                        }
                                                        property_details.append(detail)
                                                        search_summary['matches_found'] += 1
                        except Exception:
                            continue  # Skip this element if both methods fail
        
        except Exception:
            continue  # Skip this element type if it doesn't exist
    
    # Strategy 2: Search by specific property sets (if no matches found)
    if not found_values:
        search_summary['strategies_attempted'] += 1
        
        for element_type in ['IfcBuildingElementProxy', 'IfcFlowTerminal', 'IfcDistributionElement']:
            try:
                elements = ifc_file.by_type(element_type)
                
                for element in elements:
                    try:
                        psets = ifcopenshell.util.element.get_psets(element)
                        
                        for pset_name in property_sets:
                            if pset_name in psets:
                                pset_data = psets[pset_name]
                                
                                for prop_name, prop_value in pset_data.items():
                                    if any(kw in prop_name.lower() for kw in property_keywords_lower):
                                        value_str = str(prop_value)
                                        found_values.add(value_str)
                                        
                                        if include_details:
                                            detail = {
                                                'element_id': element.id(),
                                                'element_name': element.Name,
                                                'element_type': element.is_a(),
                                                'property_set': pset_name,
                                                'property_name': prop_name,
                                                'property_value': prop_value,
                                                'search_strategy': 'property_set_specific'
                                            }
                                            property_details.append(detail)
                                            search_summary['matches_found'] += 1
                    
                    except Exception:
                        continue
            
            except Exception:
                continue
    
    # Strategy 3: Broad search across all elements (last resort)
    if not found_values:
        search_summary['strategies_attempted'] += 1
        
        for element in ifc_file:
            try:
                # Only check elements with names to reduce noise
                if not element.Name:
                    continue
                    
                # Check if element might be relevant
                element_relevant = (
                    not component_keywords_lower or
                    any(kw in element.Name.lower() for kw in component_keywords_lower) or
                    (element.ObjectType and any(kw in element.ObjectType.lower() for kw in component_keywords_lower))
                )
                
                if element_relevant:
                    try:
                        psets = ifcopenshell.util.element.get_psets(element)
                        
                        for pset_name, pset_data in psets.items():
                            for prop_name, prop_value in pset_data.items():
                                if any(kw in prop_name.lower() for kw in property_keywords_lower):
                                    value_str = str(prop_value)
                                    found_values.add(value_str)
                                    
                                    if include_details:
                                        detail = {
                                            'element_id': element.id(),
                                            'element_name': element.Name,
                                            'element_type': element.is_a(),
                                            'property_set': pset_name,
                                            'property_name': prop_name,
                                            'property_value': prop_value,
                                            'search_strategy': 'broad_search'
                                        }
                                        property_details.append(detail)
                                        search_summary['matches_found'] += 1
                    
                    except Exception:
                        continue
            
            except Exception:
                continue
    
    return {
        'found_values': found_values,
        'property_details': property_details,
        'search_summary': search_summary,
        'components_analyzed': components_analyzed
    }