import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.selector
import ifcopenshell.util.system
from typing import List, Dict, Any, Optional
import re

def find_elements_by_semantic_category(
    ifc_file,
    semantic_category: str,
    primary_types: List[str],
    alternative_types: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    name_pattern_analysis: bool = True,
    max_examples: int = 3,
    include_direct_name_search: bool = False,
    highlight_matching_properties: bool = True,
    name_search_case_sensitive: bool = False,
    include_mep_discovery: bool = False,
    include_system_analysis: bool = False,
    mep_keywords: Optional[List[str]] = None,
    auto_discover_types: bool = False,
    system_keywords: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Finds elements of a semantic category using a comprehensive multi-strategy search approach.
    
    This function handles the common BIM challenge where elements of the same semantic meaning
    might be modeled using different IFC types or naming conventions. It implements:
    1) Direct IFC type search for expected types
    2) Alternative type discovery and analysis
    3) Keyword matching in element names and properties
    4) Name pattern analysis for categorization
    5) Direct name-based search (optional)
    6) Property highlighting for matching keywords (optional)
    7) MEP/electrical system discovery (optional)
    8) System-level analysis (optional)
    9) Automatic type discovery (optional)
    10) Comprehensive reporting of findings with counts and examples
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        semantic_category: String describing the semantic category (e.g., 'columns', 'doors', 'lighting')
        primary_types: List of expected IFC types for this category
        alternative_types: List of fallback IFC types to search if primary types yield no results
        keywords: List of search keywords in multiple languages
        name_pattern_analysis: Whether to enable name pattern grouping
        max_examples: Maximum number of examples to show per category
        include_direct_name_search: Whether to perform simple name-based searches for elements containing the semantic category or keywords
        highlight_matching_properties: Whether to highlight properties that contain the semantic keywords when displaying results
        name_search_case_sensitive: Whether to control case sensitivity for direct name searches
        include_mep_discovery: Whether to automatically discover MEP/electrical related element types using keyword matching
        include_system_analysis: Whether to check IfcSystem elements for related systems
        mep_keywords: List of keywords to identify MEP-related element types (default: ['electric', 'distribution', 'flow', 'terminal', 'controller', 'segment', 'system', 'cable', 'conduit', 'fixture', 'device', 'equipment'])
        auto_discover_types: Whether to automatically find element types containing semantic keywords
        system_keywords: List of keywords for system-level keyword matching (default: same as keywords)
        
    Returns:
        Dict containing:
        - 'semantic_category': The searched category name
        - 'primary_results': Results from primary type search
        - 'alternative_results': Results from alternative type search
        - 'keyword_results': Results from keyword matching
        - 'name_patterns': Name pattern analysis (if enabled)
        - 'direct_name_search': Results from direct name search (if enabled)
        - 'mep_discovery': MEP/electrical type discovery results (if enabled)
        - 'system_analysis': System-level analysis results (if enabled)
        - 'auto_discovered_types': Automatically discovered types (if enabled)
        - 'summary': Overall summary with total counts
        - 'diagnostics': Search diagnostics and metadata
        
    Example:
        ```python
        import ifcopenshell
        
        model = ifcopenshell.open('building.ifc')
        result = find_elements_by_semantic_category(
            ifc_file=model,
            semantic_category='lighting',
            primary_types=['IfcLightFixture'],
            alternative_types=['IfcFurnishingElement', 'IfcDistributionElement'],
            keywords=['light', 'luminaire', 'leuchte'],
            include_mep_discovery=True,
            include_system_analysis=True,
            auto_discover_types=True
        )
        print(f"Found {result['summary']['total_elements_found']} lighting elements")
        ```
    """
    
    # Set default values for optional parameters
    if alternative_types is None:
        alternative_types = []
    if keywords is None:
        keywords = []
    if mep_keywords is None:
        mep_keywords = ['electric', 'distribution', 'flow', 'terminal', 'controller', 'segment', 'system', 'cable', 'conduit', 'fixture', 'device', 'equipment']
    if system_keywords is None:
        system_keywords = keywords
    
    result = {
        'semantic_category': semantic_category,
        'primary_results': {},
        'alternative_results': {},
        'keyword_results': {},
        'name_patterns': {},
        'direct_name_search': {},
        'mep_discovery': {},
        'system_analysis': {},
        'auto_discovered_types': {},
        'summary': {'total_elements_found': 0, 'search_strategies_used': []},
        'diagnostics': {'primary_types_searched': primary_types, 'alternative_types_searched': alternative_types}
    }
    
    # Initialize direct name search result if enabled
    if include_direct_name_search:
        search_terms = [semantic_category] + keywords if keywords else [semantic_category]
        result['direct_name_search'] = {
            'count': 0,
            'examples': [],
            'search_terms_used': search_terms,
            'case_sensitive': name_search_case_sensitive
        }
    
    try:
        # Strategy 0: Auto-discover types containing semantic keywords
        auto_discovered_types_list = []
        if auto_discover_types and keywords:
            all_types = set()
            for element in ifc_file:
                all_types.add(element.is_a())
            
            for ifc_type in all_types:
                if any(keyword.lower() in ifc_type.lower() for keyword in keywords):
                    auto_discovered_types_list.append(ifc_type)
            
            if auto_discovered_types_list:
                result['auto_discovered_types'] = {
                    'types_found': auto_discovered_types_list,
                    'count': len(auto_discovered_types_list)
                }
                result['summary']['search_strategies_used'].append('auto_discovered_types')
        
        # Strategy 0.5: MEP discovery
        mep_discovered_types = []
        if include_mep_discovery:
            all_types = set()
            for element in ifc_file:
                all_types.add(element.is_a())
            
            for ifc_type in all_types:
                if any(keyword.lower() in ifc_type.lower() for keyword in mep_keywords):
                    mep_discovered_types.append(ifc_type)
            
            if mep_discovered_types:
                result['mep_discovery'] = {
                    'mep_types_found': mep_discovered_types,
                    'count': len(mep_discovered_types),
                    'keywords_used': mep_keywords
                }
                result['summary']['search_strategies_used'].append('mep_discovery')
        
        # Combine all types for searching
        all_search_types = primary_types + alternative_types + auto_discovered_types_list
        
        # Strategy 1: Direct IFC type search for primary types
        primary_total = 0
        for ifc_type in primary_types:
            try:
                elements = ifc_file.by_type(ifc_type)
                if elements:
                    element_data = []
                    for element in elements[:max_examples]:
                        element_info = {
                            'GlobalId': getattr(element, 'GlobalId', None),
                            'Name': getattr(element, 'Name', None),
                            'ObjectType': getattr(element, 'ObjectType', None),
                            'PredefinedType': getattr(element, 'PredefinedType', None)
                        }
                        
                        # Add property highlighting if enabled
                        if highlight_matching_properties and keywords:
                            try:
                                psets = ifcopenshell.util.element.get_psets(element)
                                highlighted_properties = {}
                                for pset_name, pset_data in psets.items():
                                    highlighted_props = {}
                                    for prop_name, prop_value in pset_data.items():
                                        # Check if property contains any keyword
                                        prop_str = str(prop_value).lower()
                                        keyword_matches = [kw for kw in keywords if kw.lower() in prop_str]
                                        if keyword_matches:
                                            highlighted_props[prop_name] = {
                                                'value': prop_value,
                                                'matching_keywords': keyword_matches
                                            }
                                    if highlighted_props:
                                        highlighted_properties[pset_name] = highlighted_props
                                if highlighted_properties:
                                    element_info['highlighted_properties'] = highlighted_properties
                            except Exception as e:
                                result['diagnostics'][f'property_highlighting_error_{ifc_type}'] = str(e)
                        
                        element_data.append(element_info)
                    
                    result['primary_results'][ifc_type] = {
                        'count': len(elements),
                        'examples': element_data
                    }
                    primary_total += len(elements)
            except Exception as e:
                result['diagnostics'][f'primary_type_error_{ifc_type}'] = str(e)
        
        if primary_total > 0:
            result['summary']['search_strategies_used'].append('primary_types')
        
        # Strategy 2: Alternative type search (only if primary types yield no results)
        alternative_total = 0
        if primary_total == 0 and alternative_types:
            for ifc_type in alternative_types:
                try:
                    elements = ifc_file.by_type(ifc_type)
                    if elements:
                        element_data = []
                        for element in elements[:max_examples]:
                            element_info = {
                                'GlobalId': getattr(element, 'GlobalId', None),
                                'Name': getattr(element, 'Name', None),
                                'ObjectType': getattr(element, 'ObjectType', None),
                                'PredefinedType': getattr(element, 'PredefinedType', None)
                            }
                            
                            # Add property highlighting if enabled
                            if highlight_matching_properties and keywords:
                                try:
                                    psets = ifcopenshell.util.element.get_psets(element)
                                    highlighted_properties = {}
                                    for pset_name, pset_data in psets.items():
                                        highlighted_props = {}
                                        for prop_name, prop_value in pset_data.items():
                                            prop_str = str(prop_value).lower()
                                            keyword_matches = [kw for kw in keywords if kw.lower() in prop_str]
                                            if keyword_matches:
                                                highlighted_props[prop_name] = {
                                                    'value': prop_value,
                                                    'matching_keywords': keyword_matches
                                                }
                                        if highlighted_props:
                                            highlighted_properties[pset_name] = highlighted_props
                                    if highlighted_properties:
                                        element_info['highlighted_properties'] = highlighted_properties
                                except Exception as e:
                                    result['diagnostics'][f'property_highlighting_error_{ifc_type}'] = str(e)
                            
                            element_data.append(element_info)
                        
                        result['alternative_results'][ifc_type] = {
                            'count': len(elements),
                            'examples': element_data
                        }
                        alternative_total += len(elements)
                except Exception as e:
                    result['diagnostics'][f'alternative_type_error_{ifc_type}'] = str(e)
            
            if alternative_total > 0:
                result['summary']['search_strategies_used'].append('alternative_types')
        
        # Strategy 3: Keyword matching in names and properties
        keyword_matches = []
        
        if keywords:
            for ifc_type in all_search_types:
                try:
                    elements = ifc_file.by_type(ifc_type)
                    for element in elements:
                        match_found = False
                        match_reasons = []
                        
                        # Check name
                        if element.Name:
                            for keyword in keywords:
                                if keyword.lower() in element.Name.lower():
                                    match_found = True
                                    match_reasons.append(f'name_contains_{keyword}')
                        
                        # Check ObjectType
                        if element.ObjectType:
                            for keyword in keywords:
                                if keyword.lower() in str(element.ObjectType).lower():
                                    match_found = True
                                    match_reasons.append(f'objecttype_contains_{keyword}')
                        
                        if match_found:
                            element_info = {
                                'GlobalId': getattr(element, 'GlobalId', None),
                                'Name': getattr(element, 'Name', None),
                                'ObjectType': getattr(element, 'ObjectType', None),
                                'PredefinedType': getattr(element, 'PredefinedType', None),
                                'IfcType': ifc_type,
                                'match_reasons': match_reasons
                            }
                            
                            # Add property highlighting if enabled
                            if highlight_matching_properties:
                                try:
                                    psets = ifcopenshell.util.element.get_psets(element)
                                    highlighted_properties = {}
                                    for pset_name, pset_data in psets.items():
                                        highlighted_props = {}
                                        for prop_name, prop_value in pset_data.items():
                                            prop_str = str(prop_value).lower()
                                            keyword_matches_prop = [kw for kw in keywords if kw.lower() in prop_str]
                                            if keyword_matches_prop:
                                                highlighted_props[prop_name] = {
                                                    'value': prop_value,
                                                    'matching_keywords': keyword_matches_prop
                                                }
                                        if highlighted_props:
                                            highlighted_properties[pset_name] = highlighted_props
                                    if highlighted_properties:
                                        element_info['highlighted_properties'] = highlighted_properties
                                except Exception as e:
                                    result['diagnostics'][f'keyword_property_highlighting_error'] = str(e)
                            
                            keyword_matches.append(element_info)
                except Exception as e:
                    result['diagnostics'][f'keyword_search_error_{ifc_type}'] = str(e)
            
            if keyword_matches:
                result['keyword_results'] = {
                    'count': len(keyword_matches),
                    'examples': keyword_matches[:max_examples]
                }
                result['summary']['search_strategies_used'].append('keyword_matching')
        
        # Strategy 4: Name pattern analysis
        if name_pattern_analysis:
            all_elements = []
            for ifc_type in all_search_types:
                try:
                    elements = ifc_file.by_type(ifc_type)
                    all_elements.extend(elements)
                except Exception as e:
                    result['diagnostics'][f'pattern_analysis_error_{ifc_type}'] = str(e)
            
            name_patterns = {}
            for element in all_elements:
                if element.Name:
                    # Extract base name pattern (before numbers, dashes, etc.)
                    base_name = re.sub(r'[-_\d].*$', '', element.Name)
                    if base_name not in name_patterns:
                        name_patterns[base_name] = []
                    
                    element_info = {
                        'GlobalId': getattr(element, 'GlobalId', None),
                        'Name': getattr(element, 'Name', None),
                        'ObjectType': getattr(element, 'ObjectType', None),
                        'PredefinedType': getattr(element, 'PredefinedType', None),
                        'IfcType': element.is_a()
                    }
                    
                    # Add property highlighting if enabled
                    if highlight_matching_properties and keywords:
                        try:
                            psets = ifcopenshell.util.element.get_psets(element)
                            highlighted_properties = {}
                            for pset_name, pset_data in psets.items():
                                highlighted_props = {}
                                for prop_name, prop_value in pset_data.items():
                                    prop_str = str(prop_value).lower()
                                    keyword_matches_prop = [kw for kw in keywords if kw.lower() in prop_str]
                                    if keyword_matches_prop:
                                        highlighted_props[prop_name] = {
                                            'value': prop_value,
                                            'matching_keywords': keyword_matches_prop
                                        }
                                if highlighted_props:
                                    highlighted_properties[pset_name] = highlighted_props
                            if highlighted_properties:
                                element_info['highlighted_properties'] = highlighted_properties
                        except Exception as e:
                            result['diagnostics'][f'pattern_property_highlighting_error'] = str(e)
                    
                    name_patterns[base_name].append(element_info)
            
            # Sort patterns by count
            sorted_patterns = dict(sorted(name_patterns.items(), key=lambda x: len(x[1]), reverse=True))
            
            for pattern, elements in sorted_patterns.items():
                result['name_patterns'][pattern] = {
                    'count': len(elements),
                    'examples': elements[:max_examples]
                }
            
            if name_patterns:
                result['summary']['search_strategies_used'].append('name_pattern_analysis')
        
        # Strategy 5: Direct name search
        direct_name_matches = []
        if include_direct_name_search:
            search_terms = [semantic_category] + keywords if keywords else [semantic_category]
            
            # Search across all element types
            try:
                all_elements = ifc_file.by_type('IfcElement')
                for element in all_elements:
                    if element.Name:
                        name_match = False
                        match_terms = []
                        
                        for term in search_terms:
                            if name_search_case_sensitive:
                                if term in element.Name:
                                    name_match = True
                                    match_terms.append(term)
                            else:
                                if term.lower() in element.Name.lower():
                                    name_match = True
                                    match_terms.append(term)
                        
                        if name_match:
                            element_info = {
                                'GlobalId': getattr(element, 'GlobalId', None),
                                'Name': getattr(element, 'Name', None),
                                'ObjectType': getattr(element, 'ObjectType', None),
                                'PredefinedType': getattr(element, 'PredefinedType', None),
                                'IfcType': element.is_a(),
                                'matched_terms': match_terms
                            }
                            
                            # Add property highlighting if enabled
                            if highlight_matching_properties and keywords:
                                try:
                                    psets = ifcopenshell.util.element.get_psets(element)
                                    highlighted_properties = {}
                                    for pset_name, pset_data in psets.items():
                                        highlighted_props = {}
                                        for prop_name, prop_value in pset_data.items():
                                            prop_str = str(prop_value).lower()
                                            keyword_matches_prop = [kw for kw in keywords if kw.lower() in prop_str]
                                            if keyword_matches_prop:
                                                highlighted_props[prop_name] = {
                                                    'value': prop_value,
                                                    'matching_keywords': keyword_matches_prop
                                                }
                                        if highlighted_props:
                                            highlighted_properties[pset_name] = highlighted_props
                                    if highlighted_properties:
                                        element_info['highlighted_properties'] = highlighted_properties
                                except Exception as e:
                                    result['diagnostics'][f'direct_name_property_highlighting_error'] = str(e)
                            
                            direct_name_matches.append(element_info)
                
                # Update direct name search results
                result['direct_name_search']['count'] = len(direct_name_matches)
                result['direct_name_search']['examples'] = direct_name_matches[:max_examples]
                
                if direct_name_matches:
                    result['summary']['search_strategies_used'].append('direct_name_search')
                                
            except Exception as e:
                result['diagnostics']['direct_name_search_error'] = str(e)
        
        # Strategy 6: System analysis
        if include_system_analysis:
            try:
                systems = ifc_file.by_type('IfcSystem')
                relevant_systems = []
                
                for system in systems:
                    system_name = getattr(system, 'Name', '') or ''
                    system_obj_type = getattr(system, 'ObjectType', '') or ''
                    combined_system_text = (system_name + ' ' + system_obj_type).lower()
                    
                    # Check if system matches our keywords
                    if system_keywords and any(keyword.lower() in combined_system_text for keyword in system_keywords):
                        system_info = {
                            'GlobalId': getattr(system, 'GlobalId', None),
                            'Name': system_name,
                            'ObjectType': system_obj_type,
                            'IfcType': system.is_a(),
                            'matched_keywords': [kw for kw in system_keywords if kw.lower() in combined_system_text]
                        }
                        
                        # Get elements in this system
                        try:
                            system_elements = ifcopenshell.util.system.get_system_elements(system)
                            system_info['element_count'] = len(system_elements)
                            system_info['element_types'] = list(set(elem.is_a() for elem in system_elements))
                            if system_elements:
                                system_info['element_examples'] = [
                                    {
                                        'GlobalId': getattr(elem, 'GlobalId', None),
                                        'Name': getattr(elem, 'Name', None),
                                        'IfcType': elem.is_a()
                                    } for elem in system_elements[:max_examples]
                                ]
                        except Exception as e:
                            result['diagnostics']['system_elements_error'] = str(e)
                        
                        relevant_systems.append(system_info)
                
                if relevant_systems:
                    result['system_analysis'] = {
                        'count': len(relevant_systems),
                        'systems': relevant_systems,
                        'keywords_used': system_keywords
                    }
                    result['summary']['search_strategies_used'].append('system_analysis')
                else:
                    result['system_analysis'] = {
                        'count': 0,
                        'message': 'No relevant systems found',
                        'keywords_used': system_keywords
                    }
                        
            except Exception as e:
                result['diagnostics']['system_analysis_error'] = str(e)
        
        # Calculate total elements found
        total_found = primary_total + alternative_total
        if keyword_matches:
            total_found = max(total_found, len(keyword_matches))  # Avoid double counting
        if include_direct_name_search and direct_name_matches:
            total_found = max(total_found, len(direct_name_matches))  # Avoid double counting
        
        result['summary']['total_elements_found'] = total_found
        
    except Exception as e:
        result['diagnostics']['general_error'] = str(e)
    
    return result