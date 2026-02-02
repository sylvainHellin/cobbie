import ifcopenshell
from typing import Dict, List, Optional

def get_element_type_distribution(
    model: ifcopenshell.file, 
    root_type: Optional[str] = 'IfcElement', 
    exclude_types: Optional[List[str]] = None
) -> Dict[str, int]:
    """
    Calculates the frequency distribution of IFC elements based on their entity type (is_a).
    
    This function retrieves all instances of a specified root type (e.g., IfcElement, 
    IfcDistributionElement) or all entities in the model if root_type is None.
    It returns a count of each specific subtype found. It is useful for generating 
    inventories, understanding model composition, verifying element types present 
    in the model, and discovering available schema entities.

    Args:
        model (ifcopenshell.file): The IFC model instance.
        root_type (Optional[str]): The parent IFC class to analyze. Defaults to 'IfcElement'. 
                                  If None, iterates through all entities in the model for 
                                  comprehensive analysis.
        exclude_types (Optional[List[str]]): A list of IFC type names to exclude from the count 
                                             (e.g., ['IfcDistributionPort']). Defaults to None.

    Returns:
        Dict[str, int]: A dictionary where keys are IFC type names (e.g., 'IfcWall') 
                        and values are the counts of that type.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Get all element types (default behavior)
        >>> distribution = get_element_type_distribution(model)
        >>> # Get ALL entity types in the model (for domain discovery)
        >>> all_types = get_element_type_distribution(model, root_type=None)
        >>> # Get only distribution elements, excluding ports
        >>> vent_dist = get_element_type_distribution(
        ...     model, 
        ...     root_type='IfcDistributionElement',
        ...     exclude_types=['IfcDistributionPort']
        ... )
    """
    if not model:
        raise ValueError("IFC model instance cannot be None or empty.")
        
    if exclude_types is None:
        exclude_types = []
        
    # Optimization: Use a set for faster exclusion checking
    exclude_set = set(exclude_types)
    
    elements_iterator = None
    
    if root_type is None:
        # Iterate over all entities in the model
        elements_iterator = model
    else:
        # Retrieve elements; by_type returns empty list if type is not found, which is fine
        try:
            elements_iterator = model.by_type(root_type)
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve elements of type '{root_type}': {e}")

    distribution: Dict[str, int] = {}
    skipped_count = 0

    for element in elements_iterator:
        try:
            elem_type = element.is_a()
        except AttributeError:
            # Defensive programming: handle instances where type identification fails
            skipped_count += 1
            continue
        
        if elem_type in exclude_set:
            continue
            
        distribution[elem_type] = distribution.get(elem_type, 0) + 1

    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} elements due to missing type attributes.")

    return distribution