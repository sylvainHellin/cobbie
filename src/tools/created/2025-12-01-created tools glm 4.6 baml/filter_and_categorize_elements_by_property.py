import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def filter_and_categorize_elements_by_property(
    ifc_file: ifcopenshell.file,
    element_type: str,
    filter_property: str,
    filter_values: List[Union[str, bool, int, float]],
    categorize_field: str = 'ObjectType',
    property_set_name: Optional[str] = None,
    include_examples: int = 2,
    sort_by_count: bool = True,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Filters IFC elements by type and property condition, then categorizes and counts them by a specified field.
    
    This function handles the common BIM analysis pattern of finding elements that meet specific 
    criteria (e.g., exterior walls, fire-rated doors, load-bearing columns) and providing 
    quantitative breakdowns by their classification.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcDoor')
        filter_property: Property name to filter by (e.g., 'IsExternal', 'LoadBearing', 'FireRating')
        filter_values: List of values that match the filter condition (e.g., [True, 'TRUE'] for IsExternal)
        categorize_field: Field to categorize results by (default: 'ObjectType', options: 'Name', 'PredefinedType')
        property_set_name: Optional specific property set to search in (default: searches all)
        include_examples: Number of example elements to include per category (default: 2)
        sort_by_count: Whether to sort results by count (default: True)
        case_sensitive: Whether property value matching is case sensitive (default: False)
    
    Returns:
        Dict with:
        - total_elements: Total elements matching filter
        - categories: Dict mapping category names to {count, examples}
        - unmatched_elements: Count of elements that didn't match filter
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = filter_and_categorize_elements_by_property(
        ...     model, 'IfcWall', 'IsExternal', [True], 'ObjectType'
        ... )
        >>> print(f"Found {result['total_elements']} exterior walls")
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Prepare filter values for comparison
        normalized_filter_values = []
        for value in filter_values:
            if isinstance(value, str) and not case_sensitive:
                normalized_filter_values.append(value.lower())
            else:
                normalized_filter_values.append(value)
        
        # Filter elements by property condition
        matching_elements = []
        unmatched_count = 0
        
        for element in elements:
            matches_filter = False
            
            # Get all property sets for the element
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Search for the filter property
            for pset_name, pset_data in psets.items():
                # Skip if property_set_name is specified and doesn't match
                if property_set_name and pset_name != property_set_name:
                    continue
                
                # Check if the filter property exists in this property set
                if filter_property in pset_data:
                    property_value = pset_data[filter_property]
                    
                    # Normalize for comparison if needed
                    compare_value = property_value
                    if isinstance(property_value, str) and not case_sensitive:
                        compare_value = property_value.lower()
                    
                    # Check if the property value matches any of the filter values
                    if compare_value in normalized_filter_values:
                        matches_filter = True
                        break
            
            if matches_filter:
                matching_elements.append(element)
            else:
                unmatched_count += 1
        
        # Categorize matching elements
        categories = {}
        
        for element in matching_elements:
            # Get the categorization value
            category_value = 'Unknown'
            
            if categorize_field == 'ObjectType':
                category_value = element.ObjectType if element.ObjectType else 'Unknown'
            elif categorize_field == 'Name':
                category_value = element.Name if element.Name else 'Unknown'
            elif categorize_field == 'PredefinedType':
                category_value = element.PredefinedType if element.PredefinedType else 'Unknown'
            else:
                # Try to get the attribute directly
                if hasattr(element, categorize_field):
                    attr_value = getattr(element, categorize_field)
                    category_value = str(attr_value) if attr_value else 'Unknown'
            
            # Initialize category if not exists
            if category_value not in categories:
                categories[category_value] = {
                    'count': 0,
                    'examples': []
                }
            
            # Increment count
            categories[category_value]['count'] += 1
            
            # Add examples if needed
            if len(categories[category_value]['examples']) < include_examples:
                example_info = {
                    'GlobalId': element.GlobalId,
                    'Name': element.Name,
                    'ObjectType': element.ObjectType
                }
                categories[category_value]['examples'].append(example_info)
        
        # Sort categories by count if requested
        if sort_by_count:
            sorted_categories = dict(sorted(
                categories.items(), 
                key=lambda x: x[1]['count'], 
                reverse=True
            ))
        else:
            sorted_categories = categories
        
        return {
            'total_elements': len(matching_elements),
            'categories': sorted_categories,
            'unmatched_elements': unmatched_count
        }
        
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'total_elements': 0,
            'categories': {},
            'unmatched_elements': 0
        }