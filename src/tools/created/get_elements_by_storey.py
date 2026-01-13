import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Union, Optional


def get_elements_by_storey(
    model: ifcopenshell.file,
    ifc_type: str,
    storey_name: Union[str, List[str], None] = None,
    storey_id: Union[str, List[str], None] = None,
    include_attributes: List[str] = ['Name', 'GlobalId'],
    include_quantities: Optional[List[str]] = None,
    quantity_name: Optional[str] = None,
    include_properties: bool = False,
    include_storey_info: bool = True
) -> List[Dict[str, Any]]:
    """
    Retrieves elements of a specified IFC type contained within one or more building storeys,
    along with their attributes, properties, and quantities.

    This function abstracts the common BIM pattern of spatial containment queries—navigating
    IfcRelAggregates relationships between storeys and their contained elements.

    Args:
        model: The loaded IFC model instance
        ifc_type: The IFC element class to retrieve (e.g., 'IfcSpace', 'IfcWall', 'IfcDoor')
        storey_name: Storey name(s) to filter by. If None, returns elements from all storeys.
        storey_id: Storey GlobalId(s) to filter by. Takes precedence over storey_name if provided.
        include_attributes: Element attributes to include (default: ['Name', 'GlobalId'])
        include_quantities: Quantity names to extract (e.g., ['NetFloorArea', 'NetVolume']).
            If None, includes no quantities.
        quantity_name: Alias for include_quantities when single value needed
        include_properties: Whether to include all property sets (default: False)
        include_storey_info: Whether to include storey name/id in results (default: True)

    Returns:
        List of element dictionaries with requested attributes, quantities, and properties.
        Each dict includes 'StoreyName' and 'StoreyId' if include_storey_info is True.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> spaces = get_elements_by_storey(
        ...     model,
        ...     'IfcSpace',
        ...     storey_name='Level 1',
        ...     include_quantities=['NetFloorArea']
        ... )
        >>> for space in spaces:
        ...     print(f"{space['Name']}: {space['NetFloorArea']} m²")
    """
    # Handle quantity_name alias
    if quantity_name is not None and include_quantities is None:
        include_quantities = [quantity_name]
    elif include_quantities is None:
        include_quantities = []

    # Normalize storey_name and storey_id to lists
    if storey_name is not None and not isinstance(storey_name, list):
        storey_name = [storey_name]
    if storey_id is not None and not isinstance(storey_id, list):
        storey_id = [storey_id]

    # Find target storeys
    target_storeys = []
    all_storeys = model.by_type('IfcBuildingStorey')

    for storey in all_storeys:
        # Check by ID first (takes precedence)
        if storey_id is not None:
            if storey.GlobalId in storey_id:
                target_storeys.append(storey)
            continue

        # Check by name
        if storey_name is None:
            # Include all storeys
            target_storeys.append(storey)
        elif storey.Name is not None and storey.Name in storey_name:
            target_storeys.append(storey)

    if not target_storeys:
        if storey_name:
            print(f"Warning: No storeys found matching names: {storey_name}")
        elif storey_id:
            print(f"Warning: No storeys found matching IDs: {storey_id}")
        return []

    results = []
    skipped_count = 0

    for storey in target_storeys:
        storey_name_result = storey.Name if storey.Name else "Undefined"
        storey_id_result = storey.GlobalId

        # Get all elements in this storey
        try:
            elements = ifcopenshell.util.element.get_decomposition(storey)
        except (AttributeError, RuntimeError) as e:
            print(f"Warning: Could not get decomposition for storey {storey_name_result}: {e}")
            skipped_count += 1
            continue

        for element in elements:
            # Filter by IFC type
            if not element.is_a(ifc_type):
                continue

            element_dict = {}

            # Add storey info if requested
            if include_storey_info:
                element_dict['StoreyName'] = storey_name_result
                element_dict['StoreyId'] = storey_id_result

            # Extract requested attributes
            for attr in include_attributes:
                try:
                    value = getattr(element, attr, None)
                    element_dict[attr] = value
                except AttributeError:
                    element_dict[attr] = None

            # Extract quantities if requested
            if include_quantities:
                try:
                    qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
                    for qset_name, quantities in qtos.items():
                        for q_name in include_quantities:
                            if q_name in quantities:
                                element_dict[q_name] = quantities[q_name]
                except (AttributeError, KeyError):
                    # Quantity extraction failed, continue without quantities
                    pass

            # Extract all properties if requested
            if include_properties:
                try:
                    psets = ifcopenshell.util.element.get_psets(element, psets_only=True)
                    element_dict['Properties'] = psets
                except (AttributeError, KeyError):
                    element_dict['Properties'] = {}

            results.append(element_dict)

    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} storeys due to errors")

    return results