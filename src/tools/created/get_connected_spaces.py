import ifcopenshell
from typing import List, Dict, Any, Optional, Union


def get_connected_spaces(
    model: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    connection_type: Optional[List[str]] = None,
    return_connection_details: bool = False
) -> List[Dict[str, Any]]:
    """
    Retrieves a list of spaces (IfcSpace) connected to a target element through
    space boundaries (IfcRelSpaceBoundary).

    Connections are determined by:
    1. If the element is an IfcSpace: Finding other spaces that share the same
       RelatedBuildingElement (e.g., a door or window) in their space boundaries.
    2. If the element is an IfcBuildingElement: Finding all spaces that reference
       this element in their space boundaries.

    Args:
        model: The loaded IFC model instance.
        element: The starting element (IfcSpace or IfcBuildingElement).
        connection_type: Optional filter for the building element type creating the
            connection (e.g., ['IfcDoor'], ['IfcDoor', 'IfcWindow']). If None,
            all connections (including via walls) are returned.
        return_connection_details: If True, includes details about the connecting
            element (door/window) and the boundary instance.

    Returns:
        A list of dictionaries, each containing connected space information.
        Structure:
        {
            'space': <IfcSpace instance>,
            'space_name': <str>,
            'space_id': <str>,
            'connection_element': <IfcBuildingElement instance or None>,
            'connection_type': <str>,
            'boundary': <IfcRelSpaceBoundary instance or None>
        }

    Example Usage:
        >>> model = ifcopenshell.open('model.ifc')
        >>> room = model.by_type('IfcSpace')[0]
        >>> connected = get_connected_spaces(model, room, connection_type=['IfcDoor'])
        >>> for c in connected:
        ...     print(f"Connected to: {c['space_name']}")
    """
    if not model or not element:
        return []

    result: List[Dict[str, Any]] = []
    seen_space_ids = set()

    # Pre-compute all space boundaries and index them by RelatedBuildingElement
    # Map: Element GlobalId -> List of Boundaries
    boundaries_by_element: Dict[str, List[ifcopenshell.entity_instance]] = {}

    try:
        all_boundaries = model.by_type('IfcRelSpaceBoundary')
    except RuntimeError:
        return []

    for b in all_boundaries:
        rel_elem = getattr(b, 'RelatedBuildingElement', None)
        if rel_elem:
            eid = getattr(rel_elem, 'GlobalId', None)
            if eid:
                if eid not in boundaries_by_element:
                    boundaries_by_element[eid] = []
                boundaries_by_element[eid].append(b)

    # Case 1: Element is a Space (find neighbors via shared elements)
    if element.is_a('IfcSpace'):
        # Find all boundaries belonging to this space
        my_boundaries = [b for b in all_boundaries if getattr(b, 'RelatingSpace', None) == element]

        for boundary in my_boundaries:
            # Logic A: Shared Building Element (1st Level Boundary)
            conn_elem = getattr(boundary, 'RelatedBuildingElement', None)

            if conn_elem:
                elem_id = conn_elem.GlobalId
                elem_type = conn_elem.is_a()

                # Apply connection_type filter
                if connection_type and elem_type not in connection_type:
                    continue

                # Find all boundaries that share this building element
                if elem_id in boundaries_by_element:
                    for neighbor_boundary in boundaries_by_element[elem_id]:
                        neighbor_space = getattr(neighbor_boundary, 'RelatingSpace', None)

                        # Validate neighbor space and ensure it's not the input space
                        if neighbor_space and neighbor_space.GlobalId != element.GlobalId:
                            if neighbor_space.GlobalId not in seen_space_ids:
                                item = {
                                    'space': neighbor_space,
                                    'space_name': getattr(neighbor_space, 'Name', 'Unknown'),
                                    'space_id': neighbor_space.GlobalId
                                }
                                if return_connection_details:
                                    item['connection_element'] = conn_elem
                                    item['connection_type'] = elem_type
                                    item['boundary'] = neighbor_boundary

                                result.append(item)
                                seen_space_ids.add(neighbor_space.GlobalId)

            # Logic B: 2nd Level Boundary (ConnectedTo attribute)
            connected_to = getattr(boundary, 'ConnectedTo', None)
            if connected_to:
                connected_space = getattr(connected_to, 'RelatingSpace', None)
                if connected_space and connected_space.GlobalId != element.GlobalId:
                    # Filter check: 2nd level connections might not have a RelatedBuildingElement
                    if connection_type:
                        elem_type = getattr(conn_elem, 'is_a', None) if conn_elem else None
                        if not elem_type or elem_type not in connection_type:
                            continue

                    if connected_space.GlobalId not in seen_space_ids:
                        item = {
                            'space': connected_space,
                            'space_name': getattr(connected_space, 'Name', 'Unknown'),
                            'space_id': connected_space.GlobalId
                        }
                        if return_connection_details:
                            item['connection_element'] = conn_elem
                            item['connection_type'] = getattr(conn_elem, 'is_a', 'VirtualConnection') if conn_elem else 'VirtualConnection'
                            item['boundary'] = boundary

                        result.append(item)
                        seen_space_ids.add(connected_space.GlobalId)

    # Case 2: Element is a Building Element (find all spaces using it)
    elif element.is_a('IfcBuildingElement'):
        elem_id = getattr(element, 'GlobalId', None)
        elem_type = element.is_a()

        # Apply filter if the element itself is being queried as the connector
        if connection_type and elem_type not in connection_type:
            return []

        if elem_id and elem_id in boundaries_by_element:
            for boundary in boundaries_by_element[elem_id]:
                space = getattr(boundary, 'RelatingSpace', None)
                if space and space.GlobalId not in seen_space_ids:
                    item = {
                        'space': space,
                        'space_name': getattr(space, 'Name', 'Unknown'),
                        'space_id': space.GlobalId
                    }
                    if return_connection_details:
                        item['connection_element'] = element
                        item['connection_type'] = elem_type
                        item['boundary'] = boundary

                    result.append(item)
                    seen_space_ids.add(space.GlobalId)

    return result