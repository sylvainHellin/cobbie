import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Tuple, Optional, Any, Union

def analyze_element_types_with_specifications(
    ifc_file: ifcopenshell.file,
    element_type: str,
    categorization_property: Tuple[str, Optional[str]] = ('ObjectType', None),
    include_count: bool = True,
    max_examples_per_category: int = 1,
    property_keywords: Optional[List[str]] = None,
    sort_by_count: bool = True
) -> Dict[str, Any]:
    """
    Analyzes IFC elements of a specified type to provide comprehensive categorization with quantities and detailed technical specifications.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcColumn', 'IfcDoor')
        categorization_property: Property source for categorization as (property_set, property_name) tuple, 
                               defaults to ('ObjectType', None) for ObjectType field
        include_count: Boolean to include element counts (default: True)
        max_examples_per_category: Maximum sample elements to analyze per category for specifications (default: 1)
        property_keywords: Optional list of keywords to filter relevant properties (default: None for all properties)
        sort_by_count: Boolean to sort categories by quantity (default: True)
    
    Returns:
        Dict containing:
        - total_elements: Total count of elements
        - categories: Dict mapping category names to element counts
        - specifications: Dict mapping category names to detailed technical specifications
        - summary: List of (category, count) tuples
        
    Example:
        ```python
        import ifcopenshell
        
        # Load IFC model
        model = ifcopenshell.open('building.ifc')
        
        # Analyze column types with specifications
        result = analyze_element_types_with_specifications(
            model,
            'IfcColumn',
            categorization_property=('ObjectType', None),
            max_examples_per_category=1,
            property_keywords=['Length', 'CrossSectionArea', 'Volume']
        )
        
        print(f"Total columns: {result['total_elements']}")
        for category, count in result['summary']:
            print(f"{category}: {count} columns")
        ```
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_elements = len(elements)
        
        if total_elements == 0:
            return {
                'total_elements': 0,
                'categories': {},
                'specifications': {},
                'summary': []
            }
        
        # Categorize elements based on the specified property
        categories = {}
        category_elements = {}
        
        property_set_name, property_name = categorization_property
        
        for element in elements:
            # Determine the category value
            if property_set_name == 'ObjectType' and property_name is None:
                # Use ObjectType attribute directly
                category_value = getattr(element, 'ObjectType', None) or 'Unknown'
            else:
                # Use property set
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    if property_set_name in psets:
                        if property_name:
                            category_value = psets[property_set_name].get(property_name, 'Unknown')
                        else:
                            # Use the first property value in the set
                            category_value = list(psets[property_set_name].values())[0] if psets[property_set_name] else 'Unknown'
                    else:
                        category_value = 'Unknown'
                except:
                    category_value = 'Unknown'
            
            # Add to category
            if category_value not in categories:
                categories[category_value] = 0
                category_elements[category_value] = []
            
            categories[category_value] += 1
            category_elements[category_value].append(element)
        
        # Sort categories by count if requested
        if sort_by_count:
            sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
            categories = dict(sorted_categories)
        
        # Extract specifications for each category
        specifications = {}
        
        for category_name, category_elems in category_elements.items():
            if not category_elems:
                continue
                
            # Analyze sample elements for this category
            sample_specs = []
            num_samples = min(max_examples_per_category, len(category_elems))
            
            for i in range(num_samples):
                element = category_elems[i]
                
                # Get element basic info
                element_info = {
                    'type': element_type,
                    'name': getattr(element, 'Name', None),
                    'object_type': getattr(element, 'ObjectType', None),
                    'global_id': getattr(element, 'GlobalId', None)
                }
                
                # Get all property sets
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    
                    # Filter properties if keywords specified
                    if property_keywords:
                        filtered_psets = {}
                        for pset_name, pset_data in psets.items():
                            if isinstance(pset_data, dict):
                                filtered_data = {}
                                for prop_name, prop_value in pset_data.items():
                                    if any(keyword.lower() in prop_name.lower() for keyword in property_keywords):
                                        filtered_data[prop_name] = prop_value
                                if filtered_data:
                                    filtered_psets[pset_name] = filtered_data
                            elif any(keyword.lower() in pset_name.lower() for keyword in property_keywords):
                                filtered_psets[pset_name] = pset_data
                        psets = filtered_psets
                    
                    element_spec = {
                        'element_info': element_info,
                        'found_properties': psets,
                        'element_found': True
                    }
                    
                except Exception as e:
                    element_spec = {
                        'element_info': element_info,
                        'error': str(e),
                        'element_found': False
                    }
                
                sample_specs.append(element_spec)
            
            specifications[category_name] = {
                'count': len(category_elems),
                'sample_specifications': sample_specs
            }
        
        # Create summary
        summary = [(cat, count) for cat, count in categories.items()]
        
        return {
            'total_elements': total_elements,
            'categories': categories,
            'specifications': specifications,
            'summary': summary
        }
        
    except Exception as e:
        return {
            'total_elements': 0,
            'categories': {},
            'specifications': {},
            'summary': [],
            'error': str(e)
        }