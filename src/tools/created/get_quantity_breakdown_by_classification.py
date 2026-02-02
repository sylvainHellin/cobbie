import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Tuple, Literal, Union

def get_quantity_breakdown_by_classification(
    model: ifcopenshell.file,
    element_type: str,
    quantity_name: str,
    classification_method: Literal['predefined_type', 'type_object', 'auto'] = 'auto',
    include_individual_elements: bool = False,
    pset_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates the total quantity (volume, area, length, etc.) of elements broken down by their classification.

    This function combines classification discovery with quantity aggregation. It iterates through
    elements, groups them by PredefinedType or Type Object, sums the specified quantity for each group,
    and returns a structured breakdown.

    Args:
        model: The IFC model instance.
        element_type: IFC entity type to analyze (e.g., 'IfcSlab', 'IfcWall').
        quantity_name: Name of the quantity to retrieve (e.g., 'NetVolume', 'NetFloorArea', 'Length').
        classification_method: How to group elements.
            'predefined_type': Uses the element's PredefinedType attribute.
            'type_object': Uses the Name of the associated Type Object.
            'auto': Tries PredefinedType first, then Type Object if undefined.
        include_individual_elements: If True, includes a list of element names and their values in the breakdown.
        pset_name: Specific Property Set to check for the quantity. Defaults to searching all QTO sets.

    Returns:
        A dictionary containing the analysis results:
        {
            'total_quantity': float,      # Sum of quantity for all processed elements
            'total_elements': int,        # Total number of elements successfully processed
            'skipped_elements': int,      # Count of elements skipped due to missing data/errors
            'breakdown': {
                'CategoryName': {
                    'total': float,        # Sum for this category
                    'count': int,          # Number of elements in this category
                    'elements': Optional[List[Tuple[str, float]]]  # List of (Name, Value) if requested
                }
            }
        }

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = get_quantity_breakdown_by_classification(
        ...     model, 'IfcSlab', 'NetVolume', classification_method='auto'
        ... )
        >>> print(f"Total Volume: {result['total_quantity']}")
        >>> for category, data in result['breakdown'].items():
        ...     print(f"{category}: {data['total']}")
    """
    # Retrieve elements of the specified type
    elements = model.by_type(element_type)
    if not elements:
        return {
            'total_quantity': 0.0,
            'total_elements': 0,
            'skipped_elements': 0,
            'breakdown': {}
        }

    breakdown: Dict[str, Dict[str, Any]] = {}
    grand_total = 0.0
    processed_count = 0
    skipped_count = 0

    for elem in elements:
        try:
            # 1. Determine Classification Key
            category_key: str = "Undefined"
            
            try:
                if classification_method == 'predefined_type':
                    pd_type = getattr(elem, 'PredefinedType', None)
                    category_key = pd_type if pd_type else "Undefined"
                
                elif classification_method == 'type_object':
                    type_obj = ifcopenshell.util.element.get_type(elem)
                    if type_obj:
                        category_key = getattr(type_obj, 'Name', None) or "Undefined"
                    else:
                        category_key = "Undefined"
                
                elif classification_method == 'auto':
                    pd_type = getattr(elem, 'PredefinedType', None)
                    if pd_type:
                        category_key = pd_type
                    else:
                        type_obj = ifcopenshell.util.element.get_type(elem)
                        if type_obj:
                            category_key = getattr(type_obj, 'Name', None) or "Undefined"
                        else:
                            category_key = "Undefined"
            except AttributeError:
                # Occurs if element structure is unexpected
                category_key = "Undefined"

            # 2. Retrieve Quantity Value
            value: Optional[float] = None
            try:
                # Retrieve all quantity sets (includes inherited)
                qtos = ifcopenshell.util.element.get_psets(elem, qtos_only=True)
                
                if pset_name:
                    # Look in specific pset
                    if pset_name in qtos:
                        raw_val = qtos[pset_name].get(quantity_name)
                        if raw_val is not None:
                            value = float(raw_val)
                else:
                    # Search all quantity sets for the quantity name
                    for qset_values in qtos.values():
                        if quantity_name in qset_values:
                            raw_val = qset_values[quantity_name]
                            if raw_val is not None:
                                value = float(raw_val)
                                break
            except (AttributeError, ValueError, TypeError):
                # ValueError/TypeError if value conversion fails
                pass 

            # 3. Validate and Aggregate
            if value is None:
                skipped_count += 1
                continue
            
            # Initialize category entry if not exists
            if category_key not in breakdown:
                breakdown[category_key] = {
                    'total': 0.0,
                    'count': 0,
                    'elements': []
                }
            
            # Update Aggregates
            breakdown[category_key]['total'] += value
            breakdown[category_key]['count'] += 1
            grand_total += value
            processed_count += 1
            
            if include_individual_elements:
                elem_name = getattr(elem, 'Name', 'Unnamed')
                breakdown[category_key]['elements'].append((elem_name, value))
                
        except RuntimeError:
            # Catch critical runtime errors during element processing
            skipped_count += 1
            continue

    # Finalize structure: set elements to None if not requested
    if not include_individual_elements:
        for cat_data in breakdown.values():
            cat_data['elements'] = None

    return {
        'total_quantity': round(grand_total, 5),
        'total_elements': processed_count,
        'skipped_elements': skipped_count,
        'breakdown': breakdown
    }