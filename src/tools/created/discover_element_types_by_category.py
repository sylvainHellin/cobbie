import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union
from collections import defaultdict

def discover_element_types_by_category(
    ifc_file: ifcopenshell.file,
    semantic_category: str,
    primary_types: Optional[List[str]] = None,
    alternative_types: Optional[List[str]] = None,
    categorize_by: str = 'ObjectType',
    include_property_sets: bool = True,
    type_keywords: Optional[List[str]] = None,
    max_examples_per_type: int = 3,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Discovers and categorizes IFC elements by semantic category using a comprehensive multi-strategy search approach.
    
    This function handles the common BIM challenge where elements of the same semantic meaning 
    (e.g., columns, doors, walls) might be modeled using different IFC types or naming conventions.
    It implements: 1) Primary IFC type search for expected element types, 2) Alternative type discovery 
    when primary types are not found, 3) Semantic categorization using ObjectType, Name, and property sets, 
    4) Keyword-based filtering to identify relevant elements, 5) Comprehensive reporting with counts, 
    categories, and examples.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        semantic_category: Semantic category to search for (e.g., 'column', 'door', 'wall')
        primary_types: List of expected IFC types for this category (default: auto-mapped based on semantic_category)
        alternative_types: Additional IFC types to search when primary types yield no results 
                          (default: common structural/building element types)
        categorize_by: Field to categorize elements by - 'ObjectType', 'Name', or 'PredefinedType' (default: 'ObjectType')
        include_property_sets: Whether to search property sets for type information (default: True)
        type_keywords: Keywords to identify relevant elements in names/properties (default: derived from semantic_category)
        max_examples_per_type: Maximum examples to show per category (default: 3)
        case_sensitive: Whether keyword matching is case sensitive (default: False)
    
    Returns:
        Dict containing:
        - total_elements_found: Total count of elements matching the semantic category
        - primary_type_results: Results from primary IFC type search
        - alternative_type_results: Results from alternative type search
        - categories: Dict of element types with counts and examples
        - semantic_analysis: Summary of how elements were identified
        - recommendations: Suggestions for further analysis
    """
    
    # Default mappings for semantic categories to IFC types
    semantic_type_mappings = {
        'column': ['IfcColumn'],
        'door': ['IfcDoor'],
        'window': ['IfcWindow'],
        'wall': ['IfcWall', 'IfcWallStandardCase'],
        'slab': ['IfcSlab'],
        'beam': ['IfcBeam'],
        'roof': ['IfcRoof'],
        'stair': ['IfcStair', 'IfcStairFlight'],
        'ramp': ['IfcRamp', 'IfcRampFlight'],
        'space': ['IfcSpace'],
        'building': ['IfcBuilding'],
        'storey': ['IfcBuildingStorey']
    }
    
    # Default alternative types to search
    default_alternative_types = [
        'IfcMember', 'IfcBuildingElementProxy', 'IfcStructuralMember',
        'IfcFurnishingElement', 'IfcFlowTerminal', 'IfcFlowSegment',
        'IfcDistributionElement', 'IfcElementAssembly'
    ]
    
    # Set default primary types if not provided
    if primary_types is None:
        primary_types = semantic_type_mappings.get(semantic_category.lower(), [])
    
    # Set default alternative types if not provided
    if alternative_types is None:
        alternative_types = default_alternative_types
    
    # Set default keywords if not provided
    if type_keywords is None:
        base_keywords = [semantic_category.lower()]
        # Add common variations
        if semantic_category.lower() == 'column':
            type_keywords = ['column', 'säule', 'stütze', 'pillar', 'post']
        elif semantic_category.lower() == 'wall':
            type_keywords = ['wall', 'wand', 'mauer']
        elif semantic_category.lower() == 'door':
            type_keywords = ['door', 'tür', 'porte']
        elif semantic_category.lower() == 'window':
            type_keywords = ['window', 'fenster', 'fenêtre']
        else:
            type_keywords = base_keywords
    
    if not case_sensitive:
        type_keywords = [kw.lower() for kw in type_keywords]
    
    result = {
        'total_elements_found': 0,
        'primary_type_results': {},
        'alternative_type_results': {},
        'categories': {},
        'semantic_analysis': {
            'search_strategy': 'multi_strategy',
            'primary_types_searched': primary_types,
            'alternative_types_searched': alternative_types,
            'keywords_used': type_keywords,
            'categorization_field': categorize_by
        },
        'recommendations': []
    }
    
    all_found_elements = []
    
    # Strategy 1: Search primary types
    for ifc_type in primary_types:
        try:
            elements = ifc_file.by_type(ifc_type)
            result['primary_type_results'][ifc_type] = {
                'count': len(elements),
                'elements': elements
            }
            all_found_elements.extend(elements)
        except Exception as e:
            result['primary_type_results'][ifc_type] = {
                'count': 0,
                'error': str(e)
            }
    
    # Strategy 2: Search alternative types if primary types yielded no results
    total_primary_found = sum(r.get('count', 0) for r in result['primary_type_results'].values())
    
    if total_primary_found == 0:
        for ifc_type in alternative_types:
            try:
                elements = ifc_file.by_type(ifc_type)
                # Filter by keywords to find relevant elements
                relevant_elements = []
                for element in elements:
                    if _element_matches_keywords(element, type_keywords, case_sensitive, include_property_sets):
                        relevant_elements.append(element)
                
                if relevant_elements:
                    result['alternative_type_results'][ifc_type] = {
                        'count': len(relevant_elements),
                        'elements': relevant_elements,
                        'total_in_type': len(elements)
                    }
                    all_found_elements.extend(relevant_elements)
            except Exception as e:
                result['alternative_type_results'][ifc_type] = {
                    'count': 0,
                    'error': str(e)
                }
    
    # Strategy 3: Categorize found elements
    if all_found_elements:
        categories = defaultdict(list)
        
        for element in all_found_elements:
            category_value = _get_element_category(element, categorize_by, include_property_sets)
            if category_value:
                categories[category_value].append(element)
            else:
                categories['Unknown'].append(element)
        
        # Build categories result with examples
        for category, elements in categories.items():
            examples = []
            for i, element in enumerate(elements[:max_examples_per_type]):
                example_info = {
                    'GlobalId': getattr(element, 'GlobalId', None),
                    'Name': getattr(element, 'Name', None),
                    'ObjectType': getattr(element, 'ObjectType', None),
                    'PredefinedType': getattr(element, 'PredefinedType', None)
                }
                examples.append(example_info)
            
            result['categories'][category] = {
                'count': len(elements),
                'examples': examples
            }
    
    result['total_elements_found'] = len(all_found_elements)
    
    # Generate recommendations
    if result['total_elements_found'] == 0:
        result['recommendations'].append(
            f"No {semantic_category} elements found. Consider checking alternative semantic categories "
            f"or reviewing the model's element classification structure."
        )
    elif len(result['categories']) == 1 and 'Unknown' in result['categories']:
        result['recommendations'].append(
            f"Found {result['total_elements_found']} elements but they lack proper categorization. "
            f"Consider using a different categorize_by field or reviewing property sets."
        )
    
    return result

def _element_matches_keywords(element, keywords: List[str], case_sensitive: bool, include_property_sets: bool) -> bool:
    """Helper function to check if an element matches any of the provided keywords."""
    # Check Name
    name = getattr(element, 'Name', None)
    if name:
        check_name = name if case_sensitive else name.lower()
        if any(keyword in check_name for keyword in keywords):
            return True
    
    # Check ObjectType
    object_type = getattr(element, 'ObjectType', None)
    if object_type:
        check_object_type = object_type if case_sensitive else object_type.lower()
        if any(keyword in check_object_type for keyword in keywords):
            return True
    
    # Check PredefinedType
    predefined_type = getattr(element, 'PredefinedType', None)
    if predefined_type:
        check_predefined = predefined_type if case_sensitive else predefined_type.lower()
        if any(keyword in check_predefined for keyword in keywords):
            return True
    
    # Check property sets if requested
    if include_property_sets:
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            for pset_name, pset_properties in psets.items():
                for prop_name, prop_value in pset_properties.items():
                    if isinstance(prop_value, str):
                        check_prop = prop_value if case_sensitive else prop_value.lower()
                        if any(keyword in check_prop for keyword in keywords):
                            return True
        except:
            pass  # Ignore property set access errors
    
    return False

def _get_element_category(element, categorize_by: str, include_property_sets: bool) -> Optional[str]:
    """Helper function to get the category value for an element."""
    # Try the specified categorization field first
    if categorize_by == 'ObjectType':
        value = getattr(element, 'ObjectType', None)
        if value:
            return value
    elif categorize_by == 'Name':
        value = getattr(element, 'Name', None)
        if value:
            return value
    elif categorize_by == 'PredefinedType':
        value = getattr(element, 'PredefinedType', None)
        if value:
            return value
    
    # Fallback to other fields if primary field is empty
    for field in ['ObjectType', 'Name', 'PredefinedType']:
        if field != categorize_by:
            value = getattr(element, field, None)
            if value:
                return value
    
    # Check property sets for type information
    if include_property_sets:
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            for pset_name, pset_properties in psets.items():
                for prop_name, prop_value in pset_properties.items():
                    if any(keyword in prop_name.lower() for keyword in ['type', 'art', 'typ', 'category']):
                        if isinstance(prop_value, str) and prop_value.strip():
                            return prop_value
        except:
            pass
    
    return None