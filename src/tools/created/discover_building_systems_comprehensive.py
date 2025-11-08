import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.selector
from typing import List, Dict, Any, Optional, Union

def discover_building_systems_comprehensive(
    ifc_file: ifcopenshell.file,
    system_keywords: List[str],
    target_element_types: Optional[List[str]] = None,
    include_related_types: bool = True,
    include_systems: bool = True,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Comprehensively discovers and analyzes building systems in an IFC model using a multi-strategy approach.
    
    This function systematically searches for systems that may be represented as standard element types,
    BuildingElementProxy elements, or through property-based classifications. It implements the workflow
    that proved necessary for lighting system discovery: 1) Analyzes what element types exist in the model,
    2) Searches for domain-specific element types with schema compatibility handling, 3) Performs keyword-based
    searches across element names, object types, and properties, 4) Deep-dives into BuildingElementProxy elements
    examining their property sets and classifications, 5) Checks for related systems and distribution elements,
    6) Provides categorized results with counts and detailed examples.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        system_keywords: List of keywords related to the target system (e.g., ['light', 'licht', 'leuchte', 'lamp', 'beleuchtung', 'luminaire'] for lighting)
        target_element_types: Optional list of specific element types to prioritize (e.g., ['IfcLightFixture', 'IfcLamp'])
        include_related_types: Boolean to include analysis of related element types (default: True)
        include_systems: Boolean to include IfcSystem and IfcDistributionSystem analysis (default: True)
        include_details: Boolean to include detailed property analysis (default: True)
    
    Returns:
        Dict containing:
        - element_types_found: Dict of element types that exist in the model with counts
        - domain_elements: Elements matching domain keywords with counts and details
        - proxy_elements: BuildingElementProxy elements matching domain criteria
        - systems: Related systems found
        - summary: Overall findings and recommendations
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = discover_building_systems_comprehensive(
        ...     model,
        ...     system_keywords=['light', 'lamp', 'luminaire'],
        ...     target_element_types=['IfcLightFixture', 'IfcLamp']
        ... )
        >>> print(f"Found {len(result['domain_elements'])} lighting elements")
    """
    
    result = {
        'element_types_found': {},
        'domain_elements': [],
        'proxy_elements': [],
        'systems': [],
        'summary': {
            'total_elements_analyzed': 0,
            'domain_matches': 0,
            'proxy_matches': 0,
            'systems_found': 0,
            'recommendations': []
        }
    }
    
    try:
        # Step 1: Analyze what element types exist in the model
        all_elements = ifc_file.by_type('IfcObjectDefinition')
        element_types = {}
        for element in all_elements:
            elem_type = element.is_a()
            if elem_type not in element_types:
                element_types[elem_type] = 0
            element_types[elem_type] += 1
        
        result['element_types_found'] = {k: v for k, v in element_types.items() if v > 0}
        result['summary']['total_elements_analyzed'] = sum(element_types.values())
        
        # Step 2: Search for domain-specific element types with schema compatibility handling
        domain_elements = []
        
        # Check target element types first
        if target_element_types:
            for elem_type in target_element_types:
                try:
                    elements = ifc_file.by_type(elem_type)
                    if elements:
                        for elem in elements:
                            elem_info = {
                                'id': elem.id(),
                                'type': elem.is_a(),
                                'name': getattr(elem, 'Name', None),
                                'object_type': getattr(elem, 'ObjectType', None),
                                'description': getattr(elem, 'Description', None),
                                'match_reason': 'target_type'
                            }
                            domain_elements.append(elem_info)
                except RuntimeError:
                    # Schema doesn't support this element type
                    pass
        
        # Step 3: Perform keyword-based searches across all elements
        if include_related_types and system_keywords:
            for elem_type, count in result['element_types_found'].items():
                if count > 0 and elem_type not in ['IfcProject', 'IfcSite', 'IfcBuilding', 'IfcBuildingStorey']:
                    try:
                        elements = ifc_file.by_type(elem_type)
                        for elem in elements:
                            # Check if element matches domain keywords
                            text_to_check = ' '.join(filter(None, [
                                getattr(elem, 'Name', ''),
                                getattr(elem, 'ObjectType', ''),
                                getattr(elem, 'Description', '')
                            ])).lower()
                            
                            if any(keyword.lower() in text_to_check for keyword in system_keywords):
                                elem_info = {
                                    'id': elem.id(),
                                    'type': elem.is_a(),
                                    'name': getattr(elem, 'Name', None),
                                    'object_type': getattr(elem, 'ObjectType', None),
                                    'description': getattr(elem, 'Description', None),
                                    'match_reason': 'keyword_match'
                                }
                                
                                # Add property details if requested
                                if include_details:
                                    try:
                                        psets = ifcopenshell.util.element.get_psets(elem)
                                        elem_info['property_sets'] = psets
                                    except:
                                        elem_info['property_sets'] = {}
                                
                                domain_elements.append(elem_info)
                    except RuntimeError:
                        # Skip unsupported element types
                        continue
        
        result['domain_elements'] = domain_elements
        result['summary']['domain_matches'] = len(domain_elements)
        
        # Step 4: Deep-dive into BuildingElementProxy elements
        proxy_matches = []
        if 'IfcBuildingElementProxy' in result['element_types_found'] and system_keywords:
            proxy_elements = ifc_file.by_type('IfcBuildingElementProxy')
            
            for element in proxy_elements:
                element_info = {
                    'id': element.id(),
                    'name': getattr(element, 'Name', None),
                    'object_type': getattr(element, 'ObjectType', None),
                    'description': getattr(element, 'Description', None),
                    'property_sets': {},
                    'classifications': [],
                    'indicators': []
                }
                
                # Extract property sets
                if include_details:
                    try:
                        psets = ifcopenshell.util.element.get_psets(element)
                        element_info['property_sets'] = psets
                        
                        # Look for domain-related indicators in properties
                        for prop_set_name, props in psets.items():
                            for prop_name, prop_value in props.items():
                                if isinstance(prop_value, str):
                                    prop_lower = prop_value.lower()
                                    if any(term in prop_lower for term in system_keywords):
                                        element_info['indicators'].append(f"{prop_set_name}.{prop_name}={prop_value}")
                    except:
                        pass
                
                # Check associations (classifications)
                try:
                    for association in element.HasAssociations:
                        if association.is_a('IfcRelAssociatesClassification'):
                            classification = association.RelatingClassification
                            if hasattr(classification, 'Name'):
                                element_info['classifications'].append(classification.Name)
                                if any(term in classification.Name.lower() for term in system_keywords):
                                    element_info['indicators'].append(f"Classification={classification.Name}")
                except:
                    pass
                
                # Check ObjectType and Name for domain terms
                for field, value in [('Name', element_info['name']), ('ObjectType', element_info['object_type'])]:
                    if value and any(term in value.lower() for term in system_keywords):
                        element_info['indicators'].append(f"{field}={value}")
                
                if element_info['indicators']:
                    proxy_matches.append(element_info)
            
            result['proxy_elements'] = proxy_matches
            result['summary']['proxy_matches'] = len(proxy_matches)
        
        # Step 5: Check for related systems
        if include_systems and system_keywords:
            systems_found = []
            
            # Check IfcSystem elements
            try:
                systems = ifc_file.by_type('IfcSystem')
                for system in systems:
                    system_text = ' '.join(filter(None, [
                        getattr(system, 'Name', ''),
                        getattr(system, 'ObjectType', ''),
                        getattr(system, 'Description', '')
                    ])).lower()
                    
                    if any(keyword.lower() in system_text for keyword in system_keywords):
                        systems_found.append({
                            'id': system.id(),
                            'type': system.is_a(),
                            'name': getattr(system, 'Name', None),
                            'object_type': getattr(system, 'ObjectType', None)
                        })
            except:
                pass
            
            # Check IfcDistributionSystem elements
            try:
                distribution_systems = ifc_file.by_type('IfcDistributionSystem')
                for system in distribution_systems:
                    system_text = ' '.join(filter(None, [
                        getattr(system, 'Name', ''),
                        getattr(system, 'ObjectType', ''),
                        getattr(system, 'Description', '')
                    ])).lower()
                    
                    if any(keyword.lower() in system_text for keyword in system_keywords):
                        systems_found.append({
                            'id': system.id(),
                            'type': system.is_a(),
                            'name': getattr(system, 'Name', None),
                            'object_type': getattr(system, 'ObjectType', None)
                        })
            except:
                pass
            
            result['systems'] = systems_found
            result['summary']['systems_found'] = len(systems_found)
        
        # Step 6: Generate summary and recommendations
        total_matches = result['summary']['domain_matches'] + result['summary']['proxy_matches'] + result['summary']['systems_found']
        
        if total_matches == 0:
            if system_keywords:
                result['summary']['recommendations'].append(
                    f"No {system_keywords[0]}-related elements found. The system may not be modeled or may use non-standard representations."
                )
                if 'IfcBuildingElementProxy' in result['element_types_found']:
                    result['summary']['recommendations'].append(
                        f"Consider examining the {result['element_types_found']['IfcBuildingElementProxy']} BuildingElementProxy elements for potential system components."
                    )
        else:
            if system_keywords:
                result['summary']['recommendations'].append(
                    f"Found {total_matches} {system_keywords[0]}-related elements across multiple categories."
                )
        
    except Exception as e:
        result['summary']['recommendations'].append(f"Error during analysis: {str(e)}")
    
    return result