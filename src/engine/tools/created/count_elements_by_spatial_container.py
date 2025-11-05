import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Union, Any, Optional

def count_elements_by_spatial_container(
    ifc_file,
    element_type: str,
    container_type: str = 'IfcBuildingStorey',
    container_filter: Optional[Dict[str, Any]] = None,
    return_elements: bool = False
) -> Dict[str, Union[int, List[Any]]]:
    """
    Counts IFC elements by their spatial container with optional filtering.

    This function analyzes the spatial hierarchy of an IFC model to count or retrieve
    elements of a specific type within spatial containers like building storeys.

    Args:
        ifc_file: The opened IFC file object
        element_type: String name of IFC element type to count (e.g., 'IfcDoor', 'IfcWindow')
        container_type: String name of spatial container type (default: 'IfcBuildingStorey')
        container_filter: Dict of filtering criteria for containers
                         (e.g., {'Elevation': 0.0} for ground floor, {'Name': 'Level 2'})
        return_elements: Boolean, if True returns list of elements, if False returns count

    Returns:
        Dict mapping container names to element counts (if return_elements=False)
        or Dict mapping container names to lists of elements (if return_elements=True)

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Count doors on ground floor
        >>> result = count_elements_by_spatial_container(
        ...     model, 'IfcDoor', 'IfcBuildingStorey', {'Elevation': 0.0}
        ... )
        >>> print(result)  # {'Level 1': 8}

        >>> # Get all windows on Level 2
        >>> result = count_elements_by_spatial_container(
        ...     model, 'IfcWindow', 'IfcBuildingStorey', {'Name': 'Level 2'}, True
        ... )
        >>> print(result)  # {'Level 2': [window1, window2, ...]}
    """
    try:
        # Get all containers of the specified type
        containers = ifc_file.by_type(container_type)

        if not containers:
            return {}

        result = {}

        for container in containers:
            # Apply container filtering if specified
            if container_filter:
                matches_filter = True
                for attr_name, expected_value in container_filter.items():
                    if not hasattr(container, attr_name):
                        matches_filter = False
                        break

                    actual_value = getattr(container, attr_name)

                    # Handle numeric comparisons with tolerance
                    if isinstance(expected_value, (int, float)):
                        if isinstance(actual_value, (int, float)):
                            if abs(float(actual_value) - float(expected_value)) > 0.001:
                                matches_filter = False
                                break
                        else:
                            matches_filter = False
                            break
                    else:
                        # String comparison
                        if str(actual_value) != str(expected_value):
                            matches_filter = False
                            break

                if not matches_filter:
                    continue

            # Get container name for result key
            container_name = getattr(container, 'Name', f'Container_{container.id()}')
            if not container_name:
                container_name = f'Container_{container.id()}'

            # Get all elements contained in this container
            try:
                contained_elements = ifcopenshell.util.element.get_decomposition(container)
            except Exception as e:
                # If get_decomposition fails, try alternative approach
                contained_elements = []
                # Try to get elements through relationships
                if hasattr(container, 'ContainsElements'):
                    for rel in container.ContainsElements:
                        if hasattr(rel, 'RelatedElements'):
                            contained_elements.extend(rel.RelatedElements)

            # Filter by element type
            target_elements = []
            for elem in contained_elements:
                if elem.is_a(element_type):
                    target_elements.append(elem)

            # Store result
            if return_elements:
                result[container_name] = target_elements
            else:
                result[container_name] = len(target_elements)

        return result

    except Exception as e:
        raise ValueError(f"Error counting elements by spatial container: {str(e)}")
