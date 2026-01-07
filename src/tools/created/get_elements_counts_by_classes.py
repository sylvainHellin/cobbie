import ifcopenshell
from typing import List, Dict, Optional


def get_elements_counts_by_classes(
    model: ifcopenshell.file, 
    class_names: Optional[List[str]] = None, 
    skip_zero: bool = False,
    include_all_classes: bool = False
) -> Dict[str, int]:
    """
    Retrieves the count of elements for IFC classes in the model.

    This function can count elements for specified IFC classes or discover all classes
    present in the model. When specific classes are provided, it attempts to count
    instances of each class, safely handling schema errors. When include_all_classes is
    True, it automatically discovers all IFC classes present in the model that have
    instances and returns their counts.

    Args:
        model: The opened IFC model.
        class_names: An optional list of IFC class names to check 
                     (e.g., ['IfcFlowTerminal', 'IfcDuctSegment']).
                     Required when include_all_classes=False, ignored when include_all_classes=True.
        skip_zero: If True, excludes classes with a count of 0 from the returned dictionary.
                  Only applies when include_all_classes=False. Defaults to False.
        include_all_classes: If True, automatically discovers all IFC classes present in the
                            model that have instances and returns their counts. When True, 
                            class_names is ignored. Defaults to False.

    Returns:
        Dict[str, int]: A dictionary mapping the class name to the number of elements found.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> 
        >>> # Example 1: Count specific classes (original behavior)
        >>> classes_to_check = ['IfcWall', 'IfcDoor', 'IfcFlowTerminal']
        >>> counts = get_elements_counts_by_classes(model, classes_to_check, skip_zero=True)
        >>> print(counts)
        {'IfcWall': 150, 'IfcDoor': 50}
        >>> 
        >>> # Example 2: Discover all classes in the model
        >>> all_counts = get_elements_counts_by_classes(model, include_all_classes=True)
        >>> print(all_counts)
        {'IfcWall': 150, 'IfcDoor': 50, 'IfcWindow': 45, 'IfcSlab': 10, ...}
    """
    counts: Dict[str, int] = {}
    
    if include_all_classes:
        # Discover all classes by iterating through all instances
        # Only classes with instances will be included
        for instance in model:
            cls = instance.is_a()
            counts[cls] = counts.get(cls, 0) + 1
    else:
        # Original behavior: count only specified classes
        if not class_names:
            # Return empty dict if no class names provided
            return counts
            
        for class_name in class_names:
            try:
                # Attempt to retrieve elements by type
                elements = model.by_type(class_name)
                count = len(elements)
                
                # Add to results if not skipping zero or if count > 0
                if not skip_zero or count > 0:
                    counts[class_name] = count
                    
            except RuntimeError:
                # This occurs if the class name is not valid for the model's schema 
                # (e.g., IFC2x3 class in IFC4 model)
                # We treat schema errors as a count of 0
                if not skip_zero:
                    counts[class_name] = 0
                    
    return counts