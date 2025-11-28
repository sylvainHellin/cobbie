import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import Dict, List, Any, Optional


def analyze_mep_components_by_semantic_systems(
    ifc_file,
    mep_element_types: List[str] = ['IfcFlowTerminal', 'IfcDistributionElement', 'IfcDistributionFlowElement', 'IfcFlowController', 'IfcFlowMovingDevice', 'IfcFlowStorageDevice'],
    semantic_system_rules: Optional[Dict[str, List[str]]] = None,
    search_fields: List[str] = ['Name', 'ObjectType'],
    include_supporting_types: bool = True,
    max_examples_per_category: int = 3,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes MEP components in an IFC model and groups them by semantic systems when formal system definitions are missing.
    
    This function handles the common BIM scenario where MEP components exist but lack IfcDistributionSystem 
    relationships. It discovers MEP-related element types, categorizes components by semantic meaning using 
    name/ObjectType analysis, and provides comprehensive system groupings.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        mep_element_types: List of IFC element types to analyze
        semantic_system_rules: Dict mapping system names to keyword lists
        search_fields: Fields to search for semantic keywords
        include_supporting_types: Boolean to include related element types like IfcDistributionElementType
        max_examples_per_category: Maximum examples to show per category
        case_sensitive: Boolean for case-sensitive matching
    
    Returns:
        Dict[str, Any] with structure:
        {
            'total_components': int,
            'semantic_systems': {
                'system_name': {
                    'count': int,
                    'categories': {
                        'category_name': {
                            'count': int,
                            'examples': List[Dict]
                        }
                    }
                }
            },
            'supporting_element_types': Dict[str, int],
            'unassigned': List[Dict]
        }
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = analyze_mep_components_by_semantic_systems(model)
        >>> print(f"Total MEP components: {result['total_components']}")
    """
    
    # Default semantic system rules if not provided
    if semantic_system_rules is None:
        semantic_system_rules = {
            'plumbing': ['wc', 'toilet', 'washbasin', 'waschbecken', 'sink', 'sanitary', 'urinal', 'drain'],
            'hvac': ['duct', 'air', 'vent', 'fan', 'coil', 'heating', 'cooling', 'hvac'],
            'electrical': ['cable', 'conduit', 'switch', 'socket', 'panel', 'breaker', 'electrical'],
            'fire_protection': ['sprinkler', 'fire', 'alarm', 'detector', 'hose', 'extinguisher']
        }
    
    try:
        # Initialize result structure
        result = {
            'total_components': 0,
            'semantic_systems': {},
            'supporting_element_types': {},
            'unassigned': []
        }
        
        # Collect all MEP elements, ensuring uniqueness
        all_mep_elements = []
        seen_element_ids = set()
        element_type_counts = {}
        
        for element_type in mep_element_types:
            try:
                elements = ifc_file.by_type(element_type)
                if elements:
                    # Only add unique elements
                    unique_elements = []
                    for element in elements:
                        if element.id not in seen_element_ids:
                            seen_element_ids.add(element.id)
                            all_mep_elements.append(element)
                            unique_elements.append(element)
                    
                    if unique_elements:
                        element_type_counts[element_type] = len(unique_elements)
            except Exception as e:
                print(f"Warning: Could not process element type {element_type}: {e}")
                continue
        
        result['total_components'] = len(all_mep_elements)
        
        # Initialize semantic systems structure
        for system_name in semantic_system_rules.keys():
            result['semantic_systems'][system_name] = {
                'count': 0,
                'categories': {}
            }
        
        # Process each element and categorize semantically
        for element in all_mep_elements:
            element_info = {
                'id': element.id,
                'type': element.is_a(),
                'name': getattr(element, 'Name', ''),
                'object_type': getattr(element, 'ObjectType', ''),
                'global_id': getattr(element, 'GlobalId', '')
            }
            
            # Combine searchable text from specified fields
            searchable_text = ''
            for field in search_fields:
                if hasattr(element, field):
                    value = getattr(element, field)
                    if value:
                        searchable_text += str(value) + ' '
            
            searchable_text = searchable_text.strip()
            if not case_sensitive:
                searchable_text = searchable_text.lower()
            
            # Try to match against semantic system rules
            assigned = False
            for system_name, keywords in semantic_system_rules.items():
                matched_category = None
                
                for keyword in keywords:
                    search_keyword = keyword if case_sensitive else keyword.lower()
                    if search_keyword in searchable_text:
                        matched_category = keyword
                        break
                
                if matched_category:
                    # Add to semantic system
                    result['semantic_systems'][system_name]['count'] += 1
                    
                    # Add to category within system
                    if matched_category not in result['semantic_systems'][system_name]['categories']:
                        result['semantic_systems'][system_name]['categories'][matched_category] = {
                            'count': 0,
                            'examples': []
                        }
                    
                    category_info = result['semantic_systems'][system_name]['categories'][matched_category]
                    category_info['count'] += 1
                    
                    # Add example if under limit
                    if len(category_info['examples']) < max_examples_per_category:
                        category_info['examples'].append(element_info)
                    
                    assigned = True
                    break
            
            # If not assigned to any semantic system, add to unassigned
            if not assigned:
                result['unassigned'].append(element_info)
        
        # Include supporting element types if requested
        if include_supporting_types:
            supporting_types = ['IfcDistributionElementType', 'IfcDistributionPort', 'IfcDistributionCircuit']
            for support_type in supporting_types:
                try:
                    elements = ifc_file.by_type(support_type)
                    if elements:
                        result['supporting_element_types'][support_type] = len(elements)
                except Exception as e:
                    print(f"Warning: Could not process supporting type {support_type}: {e}")
                    continue
        
        return result
        
    except Exception as e:
        raise RuntimeError(f"Error analyzing MEP components: {e}")