import ifcopenshell
from typing import List, Dict, Any


def get_model_class_audit(model: ifcopenshell.file, sort_by: str = 'count_desc') -> List[Dict[str, Any]]:
    """
    Performs an audit of the IFC model to identify all unique IFC classes present and their respective instance counts.
    
    This function iterates through all entities in the model to discover which classes are actually used,
    rather than relying on a predefined list. It is particularly useful for exploring unknown models,
    validating model content, or identifying non-standard modeling practices (e.g., finding that elements
    are modeled as proxies).
    
    Args:
        model (ifcopenshell.file): The opened IFC model.
        sort_by (str, optional): Criteria for sorting the results. Options are 'count_desc' (default),
                                 'count_asc', or 'name' (alphabetical).
    
    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary contains 'ifc_class' (str) and
                             'count' (int), sorted according to the sort_by parameter.
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> audit = get_model_class_audit(model, sort_by='count_desc')
        >>> for item in audit[:5]:  # Show top 5 most common classes
        ...     print(f"{item['ifc_class']}: {item['count']}")
    """
    try:
        # Get all unique IFC classes present in the model
        all_classes = set()
        for entity in model:
            all_classes.add(entity.is_a())
        
        # Get counts for each class
        results = []
        for cls in all_classes:
            count = len(model.by_type(cls))
            results.append({
                'ifc_class': cls,
                'count': count
            })
        
        # Sort results based on the sort_by parameter
        if sort_by == 'count_desc':
            results.sort(key=lambda x: x['count'], reverse=True)
        elif sort_by == 'count_asc':
            results.sort(key=lambda x: x['count'])
        elif sort_by == 'name':
            results.sort(key=lambda x: x['ifc_class'])
        else:
            # Default to count_desc if invalid sort_by value provided
            results.sort(key=lambda x: x['count'], reverse=True)
        
        return results
    
    except Exception as e:
        # Handle potential errors gracefully
        print(f"Error auditing model classes: {e}")
        return []