import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def get_element_types_by_semantic_criteria(
    ifc_file: ifcopenshell.file,
    element_type: str,
    semantic_keywords: List[str],
    categorization_field: str = 'ObjectType',
    include_details: bool = False,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Finds IFC elements of a specified type that match semantic criteria and categorizes them by their properties with counts.
    
    This function combines semantic filtering with categorization to answer questions like 
    'what types of X are used for Y purpose?'.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcWall', 'IfcDoor')
        semantic_keywords: List of keywords to identify elements by function/purpose (e.g., ['Interior', 'Partition'])
        categorization_field: Field to categorize elements by (default 'ObjectType')
        include_details: Whether to include sample details for each category (default False)
        case_sensitive: Whether keyword matching should be case sensitive (default False)
    
    Returns:
        Dict[str, Any] with structure:
        {
            'total_elements': int,
            'categories': {
                'category_name': {
                    'count': int,
                    'sample': dict  # optional, if include_details=True
                }
            },
            'summary': str
        }
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = get_element_types_by_semantic_criteria(
        ...     model, 'IfcWall', ['Interior', 'Partition']
        ... )
        >>> print(result['total_elements'])
        18
    """
    try:
        # Get all elements of the specified type
        all_elements = ifc_file.by_type(element_type)
        
        if not all_elements:
            return {
                'total_elements': 0,
                'categories': {},
                'summary': f'No elements of type {element_type} found in the model.'
            }
        
        # Filter elements by semantic keywords
        filtered_elements = []
        keywords_to_check = semantic_keywords if case_sensitive else [kw.lower() for kw in semantic_keywords]
        
        for element in all_elements:
            # Get the categorization field value
            field_value = getattr(element, categorization_field, None)
            if field_value is None:
                continue
                
            field_str = str(field_value)
            search_str = field_str if case_sensitive else field_str.lower()
            
            # Check if any semantic keyword matches
            if any(keyword in search_str for keyword in keywords_to_check):
                filtered_elements.append(element)
        
        if not filtered_elements:
            return {
                'total_elements': 0,
                'categories': {},
                'summary': f'No {element_type} elements found matching semantic criteria: {semantic_keywords}'
            }
        
        # Categorize filtered elements
        categories = {}
        
        for element in filtered_elements:
            # Get categorization value
            category_value = getattr(element, categorization_field, None)
            if category_value is None:
                category_value = 'Unknown'
            
            category_name = str(category_value)
            
            # Initialize category if not exists
            if category_name not in categories:
                categories[category_name] = {
                    'count': 0,
                    'elements': []
                }
            
            categories[category_name]['count'] += 1
            categories[category_name]['elements'].append(element)
        
        # Prepare final result
        result_categories = {}
        
        for category_name, category_data in categories.items():
            result_categories[category_name] = {
                'count': category_data['count']
            }
            
            # Include sample details if requested
            if include_details and category_data['elements']:
                sample_element = category_data['elements'][0]
                sample_details = {
                    'Name': getattr(sample_element, 'Name', None),
                    'ObjectType': getattr(sample_element, 'ObjectType', None),
                    'GlobalId': getattr(sample_element, 'GlobalId', None)
                }
                
                # Try to get type information
                try:
                    element_type_obj = ifcopenshell.util.element.get_type(sample_element)
                    if element_type_obj:
                        sample_details['TypeName'] = getattr(element_type_obj, 'Name', None)
                except:
                    pass
                
                result_categories[category_name]['sample'] = sample_details
        
        # Create summary
        total_count = len(filtered_elements)
        category_count = len(categories)
        summary = f'Found {total_count} {element_type} elements matching semantic criteria, categorized into {category_count} types.'
        
        return {
            'total_elements': total_count,
            'categories': result_categories,
            'summary': summary
        }
        
    except Exception as e:
        return {
            'total_elements': 0,
            'categories': {},
            'summary': f'Error processing {element_type} elements: {str(e)}'
        }