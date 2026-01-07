from typing import Dict
import ifcopenshell


def get_distribution_by_type_object(
    model: ifcopenshell.file,
    ifc_class: str,
    type_attribute: str = 'Name',
    default_label: str = 'Undefined'
) -> Dict[str, int]:
    """
    Calculates the distribution (counts) of elements for a given IFC class based on their
    associated Type Object (e.g., IfcWindowType, IfcRailingType).

    This function abstracts the traversal of the IsTypedBy relationship to access the
    IfcTypeObject and groups instances by a specified attribute of that type.

    Args:
        model: The opened IFC model.
        ifc_class: The IFC class to analyze (e.g., 'IfcRailing', 'IfcWindow').
        type_attribute: The attribute name on the Type Object to group by.
                       Defaults to 'Name'.
        default_label: The label to use for elements that have no type relationship or
                       missing attribute. Defaults to 'Undefined'.

    Returns:
        A dictionary where keys are the type attribute values (e.g., Type Names) and
        values are the counts of elements.

    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> distribution = get_distribution_by_type_object(model, 'IfcRailing')
        >>> print(distribution)
        {'Glass Railing': 27, 'Wood Handrail': 4}
    """
    distribution: Dict[str, int] = {}
    
    try:
        elements = model.by_type(ifc_class)
    except Exception:
        return {}
    
    for element in elements:
        type_value = default_label
        
        try:
            # Check if the element has a type relationship
            if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
                for rel in element.IsTypedBy:
                    if hasattr(rel, 'RelatingType'):
                        type_obj = rel.RelatingType
                        type_value = getattr(type_obj, type_attribute, default_label)
                        # Handle None values by using default label
                        if type_value is None:
                            type_value = default_label
                        break
        except Exception:
            # If there's any error in traversal, use default label
            type_value = default_label
        
        # Ensure the key is a string
        type_key = str(type_value)
        
        # Increment count
        distribution[type_key] = distribution.get(type_key, 0) + 1
    
    return distribution