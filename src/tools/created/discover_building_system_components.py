import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.system
from typing import Dict, List, Optional, Union, Any

def discover_building_system_components(
    ifc_file,
    system_type: str,
    primary_equipment_types: Optional[List[str]] = None,
    related_equipment_types: Optional[List[str]] = None,
    semantic_keywords: Optional[Dict[str, List[str]]] = None,
    property_keywords: Optional[List[str]] = None,
    include_property_extraction: bool = True,
    max_examples_per_category: int = 5,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Discovers all components of a specific building system type using a comprehensive multi-strategy approach.
    
    This function systematically searches for system components using equipment inventory analysis,
    semantic keyword matching, property-based discovery, and distribution system analysis.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        system_type: String specifying the building system type (e.g., 'heating', 'cooling', 'ventilation', 'plumbing', 'electrical', 'fire_protection')
        primary_equipment_types: Optional list of IFC equipment types to search (defaults based on system_type)
        related_equipment_types: Optional list of related equipment types (defaults based on system_type)
        semantic_keywords: Optional dict mapping system types to keyword lists (defaults provided)
        property_keywords: Optional list of property keywords to search (defaults based on system_type)
        include_property_extraction: Boolean to extract detailed properties (default: True)
        max_examples_per_category: Maximum examples to show per category (default: 5)
        case_sensitive: Boolean for case-sensitive matching (default: False)
    
    Returns:
        Dict containing:
        - system_summary: Overall findings (components found/absent)
        - primary_equipment: Equipment inventory results
        - semantic_fixtures: Semantic search results
        - property_matches: Property-based search results
        - distribution_elements: Distribution system findings
        - total_components_found: Count of all discovered components
        - component_categories: Breakdown by component type
    """
    
    # Default configurations for different system types - much more specific now
    default_primary_equipment = {
        'heating': ['IfcBoiler', 'IfcHeatPump', 'IfcUnitaryEquipment', 'IfcCoil', 'IfcHeatExchanger'],
        'cooling': ['IfcChiller', 'IfcCoolingTower', 'IfcUnitaryEquipment', 'IfcCoil'],
        'ventilation': ['IfcAirTerminal', 'IfcFan', 'IfcDuctSegment', 'IfcDuctFitting'],
        'plumbing': ['IfcSanitaryTerminal', 'IfcPipeSegment', 'IfcPipeFitting'],
        'electrical': ['IfcElectricDistributionPoint', 'IfcLamp', 'IfcElectricAppliance'],
        'fire_protection': ['IfcFireSuppressionTerminal', 'IfcProtectiveDevice', 'IfcAlarm']
    }
    
    # Related equipment should be more conservative - only include if they're likely to be system-specific
    default_related_equipment = {
        'heating': [],  # No general distribution elements for heating - only specific equipment
        'cooling': [],  # Same for cooling
        'ventilation': ['IfcDistributionFlowElement'],  # Ventilation often uses ducts
        'plumbing': ['IfcFlowTerminal'],  # Plumbing uses flow terminals
        'electrical': [],  # Electrical has specific types
        'fire_protection': []  # Fire protection has specific types
    }
    
    default_semantic_keywords = {
        'heating': ['heating', 'varme', 'radiator', 'convector', 'boiler', 'heat', 'panel', 'element', 'oven'],
        'cooling': ['cooling', 'kjøling', 'chiller', 'ac', 'air conditioning', 'klima', 'kule'],
        'ventilation': ['ventilation', 'luft', 'fan', 'duct', 'avtrekk', 'vent', 'aggregat'],
        'plumbing': ['water', 'vann', 'pipe', 'rør', 'drain', 'avløp', 'sanitary', 'toilet', 'sink', 'dusj', 'servant', 'klossett', 'urinal', 'vask'],
        'electrical': ['electric', 'elektrisk', 'power', 'strøm', 'lighting', 'belysning', 'lampe', 'lys'],
        'fire_protection': ['fire', 'brann', 'sprinkler', 'alarm', 'safety', 'sikkerhet', 'detektor']
    }
    
    default_property_keywords = {
        'heating': ['heating', 'varme', 'heat', 'radiator', 'temperature', 'thermal', 'boiler'],
        'cooling': ['cooling', 'kjøling', 'temperature', 'chilled', 'ac'],
        'ventilation': ['air', 'luft', 'flow', 'ventilation', 'vent', 'fan'],
        'plumbing': ['water', 'vann', 'drain', 'sanitary', 'toilet', 'sink', 'pipe'],
        'electrical': ['electric', 'power', 'voltage', 'current', 'lighting'],
        'fire_protection': ['fire', 'brann', 'safety', 'alarm', 'sprinkler']
    }
    
    # Negative keywords to exclude from certain systems
    negative_keywords = {
        'heating': ['toilet', 'dusj', 'servant', 'klossett', 'urinal', 'vask', 'avløp', 'drain'],
        'cooling': ['toilet', 'dusj', 'servant', 'klossett', 'urinal', 'vask', 'avløp', 'drain'],
        'ventilation': ['toilet', 'dusj', 'servant', 'klossett', 'urinal', 'vask', 'avløp', 'drain'],
        'electrical': ['toilet', 'dusj', 'servant', 'klossett', 'urinal', 'vask', 'avløp', 'drain'],
        'fire_protection': ['toilet', 'dusj', 'servant', 'klossett', 'urinal', 'vask', 'avløp', 'drain']
    }
    
    # Use defaults if not provided
    primary_equipment_types = primary_equipment_types or default_primary_equipment.get(system_type, [])
    related_equipment_types = related_equipment_types or default_related_equipment.get(system_type, [])
    semantic_keywords = semantic_keywords or default_semantic_keywords
    property_keywords = property_keywords or default_property_keywords.get(system_type, [])
    negative_keywords_list = negative_keywords.get(system_type, [])
    
    result = {
        'system_summary': {'system_type': system_type, 'status': 'unknown'},
        'primary_equipment': {},
        'semantic_fixtures': {'total_found': 0, 'elements_by_type': {}, 'elements': []},
        'property_matches': {'elements_analyzed': 0, 'elements_with_properties': []},
        'distribution_elements': {},
        'total_components_found': 0,
        'component_categories': {}
    }
    
    # 1. Equipment Inventory Analysis - only count specific equipment types
    all_equipment_types = list(set(primary_equipment_types + related_equipment_types))
    total_equipment = 0
    
    for eq_type in all_equipment_types:
        try:
            elements = ifc_file.by_type(eq_type)
            if elements:
                equipment_info = {
                    'count': len(elements),
                    'examples': []
                }
                
                # Add examples
                for i, elem in enumerate(elements[:max_examples_per_category]):
                    elem_info = {
                        'Name': elem.Name or 'No Name',
                        'ObjectType': elem.ObjectType or 'No Type',
                        'GlobalId': elem.GlobalId
                    }
                    
                    if include_property_extraction:
                        try:
                            psets = ifcopenshell.util.element.get_psets(elem)
                            if psets:
                                elem_info['properties'] = psets
                        except:
                            pass
                    
                    equipment_info['examples'].append(elem_info)
                
                result['primary_equipment'][eq_type] = equipment_info
                total_equipment += len(elements)
        except RuntimeError:
            # Entity type not available in this schema
            continue
    
    # 2. Semantic Keyword Search - search across broader element types with negative filtering
    keywords = semantic_keywords.get(system_type, [])
    semantic_matches = []
    
    # Search in common element types that might contain system components
    search_types = ['IfcFlowTerminal', 'IfcDistributionElement', 'IfcBuildingElementProxy', 'IfcDistributionFlowElement']
    
    for eq_type in search_types:
        try:
            elements = ifc_file.by_type(eq_type)
            for elem in elements:
                match_found = False
                matched_keyword = None
                
                # Check Name and ObjectType for keywords
                searchable_text = f"{elem.Name or ''} {elem.ObjectType or ''}"
                searchable_text_lower = searchable_text.lower()
                
                # First check negative keywords to exclude
                should_exclude = False
                for neg_keyword in negative_keywords_list:
                    if neg_keyword.lower() in searchable_text_lower:
                        should_exclude = True
                        break
                
                if should_exclude:
                    continue
                
                # Then check positive keywords
                for keyword in keywords:
                    if case_sensitive:
                        if keyword in searchable_text:
                            match_found = True
                            matched_keyword = keyword
                            break
                    else:
                        if keyword.lower() in searchable_text_lower:
                            match_found = True
                            matched_keyword = keyword
                            break
                
                if match_found:
                    elem_info = {
                        'Name': elem.Name or 'No Name',
                        'ObjectType': elem.ObjectType or 'No Type',
                        'GlobalId': elem.GlobalId,
                        'matched_keyword': matched_keyword,
                        'element_type': eq_type
                    }
                    
                    if include_property_extraction:
                        try:
                            psets = ifcopenshell.util.element.get_psets(elem)
                            if psets:
                                elem_info['properties'] = psets
                        except:
                            pass
                    
                    semantic_matches.append(elem_info)
        except RuntimeError:
            continue
    
    result['semantic_fixtures']['total_found'] = len(semantic_matches)
    result['semantic_fixtures']['elements'] = semantic_matches[:max_examples_per_category]
    
    # Group semantic matches by type
    for match in semantic_matches:
        elem_type = match.get('ObjectType', 'Unknown')
        if elem_type not in result['semantic_fixtures']['elements_by_type']:
            result['semantic_fixtures']['elements_by_type'][elem_type] = 0
        result['semantic_fixtures']['elements_by_type'][elem_type] += 1
    
    # 3. Property-based Search with negative filtering
    elements_analyzed = 0
    property_matches = []
    
    for eq_type in search_types:
        try:
            elements = ifc_file.by_type(eq_type)
            for elem in elements:
                elements_analyzed += 1
                matching_properties = []
                
                # Check negative keywords first
                searchable_text = f"{elem.Name or ''} {elem.ObjectType or ''}"
                searchable_text_lower = searchable_text.lower()
                
                should_exclude = False
                for neg_keyword in negative_keywords_list:
                    if neg_keyword.lower() in searchable_text_lower:
                        should_exclude = True
                        break
                
                if should_exclude:
                    continue
                
                try:
                    psets = ifcopenshell.util.element.get_psets(elem)
                    for pset_name, pset_data in psets.items():
                        for prop_name, prop_value in pset_data.items():
                            if isinstance(prop_value, str):
                                for keyword in property_keywords:
                                    if case_sensitive:
                                        if keyword in prop_value:
                                            matching_properties.append(f"{pset_name}.{prop_name}")
                                            break
                                    else:
                                        if keyword.lower() in prop_value.lower():
                                            matching_properties.append(f"{pset_name}.{prop_name}")
                                            break
                except:
                    continue
                
                if matching_properties:
                    elem_info = {
                        'Name': elem.Name or 'No Name',
                        'ObjectType': elem.ObjectType or 'No Type',
                        'GlobalId': elem.GlobalId,
                        'matching_properties': matching_properties,
                        'element_type': eq_type
                    }
                    property_matches.append(elem_info)
        except RuntimeError:
            continue
    
    result['property_matches']['elements_analyzed'] = elements_analyzed
    result['property_matches']['elements_with_properties'] = property_matches[:max_examples_per_category]
    
    # 4. Distribution System Analysis
    distribution_types = ['IfcDistributionSystem', 'IfcSystem', 'IfcDistributionPort']
    
    for dist_type in distribution_types:
        try:
            elements = ifc_file.by_type(dist_type)
            if elements:
                dist_info = {
                    'count': len(elements),
                    'examples': []
                }
                
                for elem in elements[:max_examples_per_category]:
                    elem_info = {
                        'Name': elem.Name or 'No Name',
                        'GlobalId': elem.GlobalId
                    }
                    
                    # Try to get LongName if available
                    if hasattr(elem, 'LongName') and elem.LongName:
                        elem_info['LongName'] = elem.LongName
                    
                    dist_info['examples'].append(elem_info)
                
                result['distribution_elements'][dist_type] = dist_info
        except RuntimeError:
            continue
    
    # Calculate totals and summary
    result['total_components_found'] = (
        total_equipment + 
        len(semantic_matches) + 
        len(property_matches)
    )
    
    # Component categories breakdown
    result['component_categories'] = {
        'primary_equipment': total_equipment,
        'semantic_matches': len(semantic_matches),
        'property_matches': len(property_matches),
        'distribution_systems': sum(info.get('count', 0) for info in result['distribution_elements'].values())
    }
    
    # System summary - more intelligent classification
    has_specific_equipment = total_equipment > 0
    has_semantic_matches = len(semantic_matches) > 0
    has_property_matches = len(property_matches) > 0
    
    if has_specific_equipment or has_semantic_matches or has_property_matches:
        result['system_summary']['status'] = 'components_found'
        result['system_summary']['message'] = f"Found {result['total_components_found']} {system_type} system components"
    else:
        result['system_summary']['status'] = 'no_components_found'
        result['system_summary']['message'] = f"No {system_type} system components found in this model"
    
    return result