import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
from typing import Dict, List, Optional, Tuple, Union, Any

def find_elements_and_containers(
    model: ifcopenshell.file,
    entity_type: str,
    search_term: str,
    container_type: str = 'IfcSpace',
    exact_match: bool = False,
    return_details: bool = False
) -> Union[Dict[str, Optional[ifcopenshell.entity_instance]], List[Dict[str, Any]]]:
    """
    Finds IFC elements by name pattern and maps them to their containing spatial structures.

    This function abstracts the common pattern of locating specific equipment
    (thermostats, fire extinguishers, sensors) and determining which spaces or
    storeys they are installed in. It combines element search with spatial
    relationship traversal.

    Args:
        model: The IFC model instance
        entity_type: IFC entity type to search (e.g., 'IfcDistributionControlElement',
            'IfcFlowTerminal', 'IfcFireSuppressionTerminal', 'IfcEnergyConversionDevice')
        search_term: Substring to search for in element names (case-insensitive)
        container_type: Type of spatial container to find (default: 'IfcSpace').
            Common options: 'IfcSpace', 'IfcBuildingStorey', 'IfcBuilding'
        exact_match: Whether to require exact name match (default: False).
            If True, element name must equal search_term (case-insensitive).
            If False, search_term can be a substring of element name.
        return_details: Whether to return detailed information (default: False).
            If False, returns dict mapping element names to container entities.
            If True, returns list of dicts with element, container, coordinates,
            attributes, and property sets.

    Returns:
        If return_details is False (default):
            Dictionary mapping element names to their container entities.
            Keys are element names (strings), values are container entity instances
            (ifcopenshell.entity_instance) or None if no container is found.

        If return_details is True:
            List of dictionaries, each containing:
            - 'element': The IFC entity instance
            - 'container': The found spatial container (IfcSpace/IfcBuildingStorey, etc.)
            - 'coordinates': Tuple (x, y, z) extracted from ObjectPlacement, or None
            - 'attributes': Dict of basic attributes (Name, GlobalId, ObjectType, PredefinedType, Tag)
            - 'psets': Dict of all property sets

        Note: If no elements match the search criteria, returns an empty dict or list.
        Elements without names are skipped and counted in a warning message.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building_model.ifc')
        >>> # Find thermostats and their containing spaces (simple mode)
        >>> result = find_elements_and_containers(
        ...     model,
        ...     'IfcDistributionControlElement',
        ...     'thermostat',
        ...     container_type='IfcSpace'
        ... )
        >>> for elem_name, container in result.items():
        ...     print(f"{elem_name} is in space {container.Name}")
        ...
        M_Thermostat:Thermostat:Thermostat:610734 is in space A102
        M_Thermostat:Thermostat:Thermostat:610678 is in space B102

        >>> # Find boilers with full details
        >>> result = find_elements_and_containers(
        ...     model,
        ...     'IfcEnergyConversionDevice',
        ...     'boiler',
        ...     return_details=True
        ... )
        >>> for item in result:
        ...     print(f"{item['attributes']['Name']} at {item['coordinates']}")
        ...     print(f"  Capacity: {item['psets'].get('PSet_Revit_Mechanical', {}).get('Output Heat')}")
    """
    # Validate inputs
    if not model:
        return {} if not return_details else []

    if not search_term:
        return {} if not return_details else []

    # Get all elements of the specified type
    elements = model.by_type(entity_type)

    if not elements:
        return {} if not return_details else []

    skipped = 0
    
    if return_details:
        result: List[Dict[str, Any]] = []
    else:
        result: Dict[str, Optional[ifcopenshell.entity_instance]] = {}

    for elem in elements:
        # Safely get element name with default
        elem_name = getattr(elem, 'Name', None)

        # Skip elements without names
        if elem_name is None:
            skipped += 1
            continue

        # Convert to string if it's not already
        elem_name_str = str(elem_name)

        # Filter by search term (case-insensitive)
        if exact_match:
            if search_term.lower() != elem_name_str.lower():
                continue
        else:
            if search_term.lower() not in elem_name_str.lower():
                continue

        # Find the container of specified type
        container = None
        try:
            container = ifcopenshell.util.element.get_container(elem, ifc_class=container_type)
        except (AttributeError, RuntimeError):
            # Handle cases where container cannot be determined
            pass

        if return_details:
            # Extract coordinates from ObjectPlacement
            coordinates = None
            try:
                placement = elem.ObjectPlacement
                if placement:
                    matrix = ifcopenshell.util.placement.get_local_placement(placement)
                    coords = matrix[:, 3][:3]
                    coordinates = (float(coords[0]), float(coords[1]), float(coords[2]))
            except (AttributeError, IndexError, TypeError, RuntimeError):
                pass

            # Extract basic attributes
            attributes = {
                'Name': elem_name_str,
                'GlobalId': getattr(elem, 'GlobalId', None),
                'ObjectType': getattr(elem, 'ObjectType', None),
                'PredefinedType': getattr(elem, 'PredefinedType', None),
                'Tag': getattr(elem, 'Tag', None)
            }

            # Get all property sets
            psets = {}
            try:
                psets = ifcopenshell.util.element.get_psets(elem)
            except (AttributeError, RuntimeError):
                pass

            result.append({
                'element': elem,
                'container': container,
                'coordinates': coordinates,
                'attributes': attributes,
                'psets': psets
            })
        else:
            # Simple mode: just map name to container
            result[elem_name_str] = container

    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements without names")

    return result