import ifcopenshell
from typing import Dict, List, Union, Optional


def group_elements_in_spatial_container(
    model: ifcopenshell.file,
    container_name: Optional[str] = None,
    element_type: str = 'IfcSpace',
    group_by_attribute: str = 'LongName',
    container_type: str = 'IfcBuildingStorey',
    return_counts: bool = False,
    search_attributes: List[str] = ['Name', 'LongName']
) -> Union[
    Dict[str, Dict[str, Union[List[int], int]]],  # When container_name is None
    Dict[str, Union[List[int], int]]  # When container_name is specified
]:
    """
    Groups IFC elements within spatial container(s) by a specified attribute value.
    Supports both single-container analysis and distribution analysis across ALL containers.

    Args:
        model: The IFC model instance.
        container_name: Name of the spatial container to search (e.g., 'GROUND FLOOR', 'Level 1').
            If None (default), analyzes ALL containers of the specified container_type.
        element_type: IFC type of elements to find (e.g., 'IfcSpace', 'IfcWindow', 'IfcDoor').
        group_by_attribute: Attribute name to group elements by (default: 'LongName').
            Common values: 'LongName', 'Name', 'ObjectType'.
        container_type: IFC type of container (default: 'IfcBuildingStorey').
        return_counts: If True, returns counts per group instead of element lists (default: False).
        search_attributes: List of attributes to search for container_name (default: ['Name', 'LongName']).
            Only used when container_name is specified.

    Returns:
        When container_name is specified:
            Dict mapping attribute values to lists of element IDs (if return_counts=False)
            or counts (if return_counts=True).
        When container_name is None:
            Nested Dict mapping container names to grouping dicts. Each inner dict
            maps attribute values to element ID lists or counts.

    Examples:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Group spaces on ground floor by function (LongName) - OLD USAGE
        >>> spaces = group_elements_in_spatial_container(model, 'GROUND FLOOR', 'IfcSpace', 'LongName')
        >>> print(spaces)
        {'LIVING ROOM': [69, 87], 'KITCHEN': [104]}

        >>> # Get counts of windows on a floor by type - OLD USAGE
        >>> counts = group_elements_in_spatial_container(model, 'Level 1', 'IfcWindow', 'OperationType', return_counts=True)
        >>> print(counts)
        {'DOUBLE_PANEL_SINGLE_SWING': 5}

        >>> # NEW USAGE: Get spaces per floor with counts
        >>> all_spaces = group_elements_in_spatial_container(model, None, 'IfcSpace', return_counts=True)
        >>> print(all_spaces)
        {'Level 1': {'LIVING': 2, 'KITCHEN': 1}, 'Level 2': {'BEDROOM': 2}}

        >>> # NEW USAGE: Get all spaces per floor with full element IDs
        >>> all_spaces_detail = group_elements_in_spatial_container(model, None, 'IfcSpace')
        >>> for floor, groups in all_spaces_detail.items():
        ...     print(f'{floor}: {len(groups)} groups')
    """
    # Validate inputs
    if model is None:
        return {} if container_name is not None else {}
    if not element_type:
        return {} if container_name is not None else {}

    # Import here to avoid issues if ifcopenshell is not available
    try:
        from ifcopenshell.util import element as util_element
    except ImportError:
        return {} if container_name is not None else {}

    # Helper function to get elements from a container
    def _get_elements_from_container(container: ifcopenshell.entity_instance) -> List[ifcopenshell.entity_instance]:
        """Extract elements of type element_type from a container."""
        elements = []
        try:
            # Use get_decomposition to get all elements in the container
            all_decomposed = util_element.get_decomposition(container)
            for elem in all_decomposed:
                if elem.is_a() == element_type:
                    elements.append(elem)
        except (AttributeError, RuntimeError):
            # Fallback to manual traversal if get_decomposition fails
            if hasattr(container, 'IsDecomposedBy'):
                for rel in container.IsDecomposedBy:
                    if hasattr(rel, 'RelatedObjects'):
                        for obj in rel.RelatedObjects:
                            if obj.is_a() == element_type:
                                elements.append(obj)
            if hasattr(container, 'ContainsElements'):
                for rel in container.ContainsElements:
                    if hasattr(rel, 'RelatedElements'):
                        for obj in rel.RelatedElements:
                            if obj.is_a() == element_type:
                                elements.append(obj)
        return elements

    # Helper function to group elements by attribute
    def _group_elements(elements: List[ifcopenshell.entity_instance]) -> Dict[str, List[int]]:
        """Group elements by the specified attribute."""
        grouped: Dict[str, List[int]] = {}
        for elem in elements:
            try:
                key = getattr(elem, group_by_attribute, None)
                if key is None:
                    key = "Undefined"
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(elem.id())
            except (AttributeError, RuntimeError):
                continue
        return grouped

    # Helper function to apply return_counts
    def _apply_counts(grouped: Dict[str, List[int]]) -> Dict[str, int]:
        return {k: len(v) for k, v in grouped.items()}

    # Main logic
    if container_name is not None:
        # OLD BEHAVIOR: Find specific container
        container = None
        try:
            for entity in model.by_type(container_type):
                for attr in search_attributes:
                    val = getattr(entity, attr, None)
                    if val and val == container_name:
                        container = entity
                        break
                if container:
                    break
        except Exception:
            return {}

        if not container:
            return {}

        # Get elements and group them
        elements = _get_elements_from_container(container)
        grouped = _group_elements(elements)

        if return_counts:
            return _apply_counts(grouped)
        return grouped
    else:
        # NEW BEHAVIOR: Analyze ALL containers
        result: Dict[str, Dict[str, Union[List[int], int]]] = {}
        
        try:
            containers = model.by_type(container_type)
        except Exception:
            return {}
        
        for container in containers:
            try:
                # Get container name for the outer dictionary key
                c_name = getattr(container, 'Name', None)
                if c_name is None:
                    c_name = getattr(container, 'LongName', 'Unknown')
                
                # Get elements and group them
                elements = _get_elements_from_container(container)
                
                if not elements:
                    continue  # Skip empty containers
                
                grouped = _group_elements(elements)
                
                if return_counts:
                    result[c_name] = _apply_counts(grouped)
                else:
                    result[c_name] = grouped
            except (AttributeError, RuntimeError):
                continue
        
        return result