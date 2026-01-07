import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Union, Any

def get_distribution_by_pset_property(
    elements: Optional[List[ifcopenshell.entity_instance]] = None,
    pset_name: str = "",
    prop_name: str = "",
    default_label: str = 'Undefined',
    model: Optional[ifcopenshell.file] = None,
    ifc_class: Optional[str] = None,
    return_proportions: bool = False
) -> Dict[str, Union[int, float]]:
    """
    Calculates the distribution (counts or proportions) of elements based on the values of a specific property within a Property Set.

    This helper abstracts the logic of iterating through elements, retrieving Property Sets,
    extracting a specific property value, and counting occurrences. It can accept a list of
    elements directly or retrieve elements from a model based on their class.

    Args:
        elements (Optional[List[ifcopenshell.entity_instance]]): The list of elements to analyze.
            Required if `model` and `ifc_class` are not provided.
        pset_name (str): The exact name of the Property Set (e.g., 'Pset_WallCommon').
        prop_name (str): The exact name of the Property to group by (e.g., 'LoadBearing').
        default_label (str, optional): The label to use if the property or pset is missing (default: 'Undefined').
        model (Optional[ifcopenshell.file]): The IFC model instance. If provided along with `ifc_class`,
            elements are retrieved automatically.
        ifc_class (Optional[str]): The IFC class to retrieve elements from (e.g., 'IfcWall').
            Required if `model` is provided.
        return_proportions (bool): If True, returns the distribution as proportions (floats between
            0.0 and 1.0) instead of raw counts. Defaults to False.

    Returns:
        Dict[str, Union[int, float]]: A dictionary mapping property values to their counts (int) or
            proportions (float).

    Raises:
        ValueError: If neither `elements` nor (`model` and `ifc_class`) are provided.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Old usage: pass elements directly
        >>> walls = model.by_type('IfcWall')
        >>> dist_counts = get_distribution_by_pset_property(walls, 'Pset_WallCommon', 'LoadBearing')
        >>> print(dist_counts) # {'True': 14, 'False': 50}
        >>>
        >>> # New usage: pass model and class, get proportions
        >>> dist_props = get_distribution_by_pset_property(
        ...     model=model, ifc_class='IfcWall',
        ...     pset_name='Pset_WallCommon', prop_name='LoadBearing',
        ...     return_proportions=True
        ... )
        >>> print(dist_props) # {'True': 0.21875, 'False': 0.78125}
    """
    # Determine source of elements
    target_elements: List[ifcopenshell.entity_instance] = []

    if model is not None and ifc_class is not None:
        # Retrieve elements internally
        target_elements = model.by_type(ifc_class)
    elif elements is not None:
        # Use provided elements list
        target_elements = elements
    else:
        raise ValueError("Either 'elements' list or both 'model' and 'ifc_class' must be provided.")

    distribution_counts: Dict[str, int] = {}

    for element in target_elements:
        try:
            # Retrieve all property sets for the element using IfcOpenShell utility
            psets = ifcopenshell.util.element.get_psets(element)

            value = default_label

            # Check if the requested Property Set exists
            if pset_name in psets:
                properties = psets[pset_name]

                # Check if the requested Property exists within the set
                if prop_name in properties:
                    raw_value = properties[prop_name]
                    # Ensure the value is string for consistent dictionary keys, handle None
                    value = str(raw_value) if raw_value is not None else default_label

            # Update the count for this value
            distribution_counts[value] = distribution_counts.get(value, 0) + 1

        except Exception:
            # Handle any unexpected errors gracefully by assigning default label
            distribution_counts[default_label] = distribution_counts.get(default_label, 0) + 1

    if return_proportions:
        total_elements = sum(distribution_counts.values())
        if total_elements == 0:
            return {k: 0.0 for k in distribution_counts.keys()}
        
        return {
            k: (v / total_elements) 
            for k, v in distribution_counts.items()
        }
    else:
        return distribution_counts