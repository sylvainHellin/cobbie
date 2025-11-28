import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.selector
from typing import List, Dict, Any, Optional
import re

def find_elements_by_semantic_category(
    ifc_file,
    semantic_category: str,
    primary_types: List[str],
    alternative_types: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    name_pattern_analysis: bool = True,
    max_examples: int = 3
) -> Dict[str, Any]:
    """
    Finds elements of a semantic category using a comprehensive multi-strategy search approach.
    
    This function handles the common BIM challenge where elements of the same semantic meaning
    might be modeled using different IFC types or naming conventions. It implements:
    1) Direct IFC type search for expected types
    2) Alternative type discovery and analysis
    3) Keyword matching in element names and properties
    4) Name pattern analysis for categorization
    5) Comprehensive reporting of findings with counts and examples
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        semantic_category: String describing the semantic category (e.g., 'columns', 'doors')
        primary_types: List of expected IFC types for this category
        alternative_types: List of fallback IFC types to search if primary types yield no results
        keywords: List of search keywords in multiple languages
        name_pattern_analysis: Whether to enable name pattern grouping
        max_examples: Maximum number of examples to show per category
        
    Returns:
        Dict containing:
        - 'semantic_category': The searched category name
        - 'primary_results': Results from primary type search
        - 'alternative_results': Results from alternative type search
        - 'keyword_results': Results from keyword matching
        - 'name_patterns': Name pattern analysis (if enabled)
        - 'summary': Overall summary with total counts
        - 'diagnostics': Search diagnostics and metadata
        
    Example:
        ```python
        import ifcopenshell
        
        model = ifcopenshell.open('building.ifc')
        result = find_elements_by_semantic_category(
            ifc_file=model,
            semantic_category='columns',
            primary_types=['IfcColumn'],
            alternative_types=['IfcMember', 'IfcBuildingElementProxy'],
            keywords=['column', 'säule', 'stütze'],
            name_pattern_analysis=True,
            max_examples=2
        )
        print(f"Found {result['summary']['total_elements_found']} columns")
        ```
    """
    
    if alternative_types is None:
        alternative_types = []
    if keywords is None:
        keywords = []
    
    result = {
        'semantic_category': semantic_category,
        'primary_results': {},
        'alternative_results': {},
        'keyword_results': {},
        'name_patterns': {},
        'summary': {'total_elements_found': 0, 'search_strategies_used': []},
        'diagnostics': {'primary_types_searched': primary_types, 'alternative_types_searched': alternative_types}
    }
    
    try:
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
        all_search_types = primary_types + alternative_types
        
        for ifc_type in all_search_types:
            try:
                elements = ifc_file.by_type(ifc_type)
                for element in elements:
                    match_found = False
                    match_reasons = []
                    
                    # Check name
                    if element.Name and keywords:
                        for keyword in keywords:
                            if keyword.lower() in element.Name.lower():
                                match_found = True
                                match_reasons.append(f'name_contains_{keyword}')
                    
                    # Check ObjectType
                    if element.ObjectType and keywords:
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
        
        # Calculate total elements found
        total_found = primary_total + alternative_total
        if keyword_matches:
            total_found = max(total_found, len(keyword_matches))  # Avoid double counting
        
        result['summary']['total_elements_found'] = total_found
        
    except Exception as e:
        result['diagnostics']['general_error'] = str(e)
    
    return result