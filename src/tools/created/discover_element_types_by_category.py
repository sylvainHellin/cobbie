import ifcopenshell
from typing import Dict, List, Any, Optional

def discover_element_types_by_category(
    ifc_file,
    category_filters: Optional[Dict[str, List[str]]] = None,
    min_count: int = 1,
    sort_by_count: bool = True,
    include_examples: int = 0,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Discovers all element types in an IFC model and categorizes them using semantic keyword matching.
    
    This function provides comprehensive model composition analysis by dynamically discovering
    all element types present, counting them, and grouping them into semantic categories
    (MEP, structural, architectural, etc.).
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        category_filters: Dict mapping category names to keyword lists. Default includes:
            - 'mep': ['flow', 'distribution', 'system', 'port', 'terminal', 'controller', 'moving', 'storage', 'energy', 'chamber', 'boiler', 'chiller', 'pump', 'fan', 'coil']
            - 'structural': ['beam', 'column', 'slab', 'wall', 'foundation', 'member', 'brace']
            - 'architectural': ['door', 'window', 'space', 'room', 'stair', 'railing', 'roof', 'curtain']
            - 'annotation': ['annotation', 'text', 'dimension', 'label']
            - 'geometry': ['point', 'line', 'curve', 'surface', 'shape', 'representation', 'placement']
            - 'material': ['material', 'style', 'colour', 'texture']
            - 'property': ['property', 'quantity', 'value', 'measure']
        min_count: Minimum element count to include in results (default: 1)
        sort_by_count: Whether to sort results by element count (default: True)
        include_examples: Number of example elements to include per type (default: 0)
        case_sensitive: Whether keyword matching is case sensitive (default: False)
    
    Returns:
        Dict with:
        - 'total_types': Total number of unique element types found
        - 'total_elements': Total number of elements in model
        - 'element_types': Dict of all element types with counts and examples
        - 'categorized': Dict mapping categories to matching element types
        - 'uncategorized': List of element types not matching any category
    
    Example:
        import ifcopenshell
        model = ifcopenshell.open('building.ifc')
        result = discover_element_types_by_category(model)
        print(f"Found {result['total_types']} element types")
        print(f"MEP elements: {len(result['categorized'].get('mep', []))}")
    """
    
    try:
        # Default category filters if not provided
        if category_filters is None:
            category_filters = {
                'mep': ['flow', 'distribution', 'system', 'port', 'terminal', 'controller', 'moving', 'storage', 'energy', 'chamber', 'boiler', 'chiller', 'pump', 'fan', 'coil'],
                'structural': ['beam', 'column', 'slab', 'wall', 'foundation', 'member', 'brace'],
                'architectural': ['door', 'window', 'space', 'room', 'stair', 'railing', 'roof', 'curtain'],
                'annotation': ['annotation', 'text', 'dimension', 'label'],
                'geometry': ['point', 'line', 'curve', 'surface', 'shape', 'representation', 'placement'],
                'material': ['material', 'style', 'colour', 'texture'],
                'property': ['property', 'quantity', 'value', 'measure']
            }
        
        # Discover all element types and count them
        element_types = {}
        total_elements = 0
        
        for element in ifc_file:
            element_type = element.is_a()
            if element_type not in element_types:
                element_types[element_type] = {
                    'count': 0,
                    'examples': []
                }
            element_types[element_type]['count'] += 1
            total_elements += 1
            
            # Add examples if requested
            if include_examples > 0 and len(element_types[element_type]['examples']) < include_examples:
                example_info = {
                    'id': element.id(),
                    'Name': getattr(element, 'Name', None),
                    'ObjectType': getattr(element, 'ObjectType', None),
                    'GlobalId': getattr(element, 'GlobalId', None)
                }
                element_types[element_type]['examples'].append(example_info)
        
        # Filter by minimum count
        filtered_types = {k: v for k, v in element_types.items() if v['count'] >= min_count}
        
        # Sort by count if requested
        if sort_by_count:
            sorted_types = dict(sorted(filtered_types.items(), key=lambda x: x[1]['count'], reverse=True))
        else:
            sorted_types = dict(sorted(filtered_types.items()))
        
        # Categorize element types
        categorized = {category: [] for category in category_filters.keys()}
        uncategorized = []
        
        for element_type in sorted_types.keys():
            matched_category = None
            
            for category, keywords in category_filters.items():
                for keyword in keywords:
                    if case_sensitive:
                        if keyword in element_type:
                            matched_category = category
                            break
                    else:
                        if keyword.lower() in element_type.lower():
                            matched_category = category
                            break
                
                if matched_category:
                    break
            
            if matched_category:
                categorized[matched_category].append(element_type)
            else:
                uncategorized.append(element_type)
        
        return {
            'total_types': len(sorted_types),
            'total_elements': total_elements,
            'element_types': sorted_types,
            'categorized': categorized,
            'uncategorized': uncategorized
        }
        
    except Exception as e:
        return {
            'error': f"Error analyzing IFC model: {str(e)}",
            'total_types': 0,
            'total_elements': 0,
            'element_types': {},
            'categorized': {},
            'uncategorized': []
        }