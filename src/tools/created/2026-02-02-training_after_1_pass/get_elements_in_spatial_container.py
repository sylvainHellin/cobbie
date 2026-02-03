import ifcopenshell
import ifcopenshell.util.element
from typing import List, Union

def get_elements_in_spatial_container(
    model: "ifcopenshell.file",
    container_name: str,
    element_type: str,
    container_type: str = 'IfcSpace'
) -> List["ifcopenshell.entity_instance"]:
    """
    Retrieves elements of a specified type contained within a spatial structure 
    (e.g., IfcSpace, IfcBuildingStorey) identified by a name string.

    This helper abstracts the common pattern of finding a container where the 
    friendly name might be stored in 'LongName' (while 'Name' is an ID) and 
    navigating 'IfcRelContainedInSpatialStructure' to find children.

    Args:
        model (ifcopenshell.file): The IFC model instance.
        container_name (str): The name of the spatial container to search for 
            (e.g., 'Office 13'). Matches against both 'Name' and 'LongName' attributes.
        element_type (str): The IFC type of elements to retrieve 
            (e.g., 'IfcFurnishingElement', 'IfcWindow').
        container_type (str, optional): The IFC type of the container to search within. 
            Defaults to 'IfcSpace'.

    Returns:
        List[ifcopenshell.entity_instance]: A list of elements of `element_type` 
            found within the named container. Returns an empty list if the container 
            is not found or no matching elements exist.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> furniture = get_elements_in_spatial_container(
        ...     model, 'Office 13', 'IfcFurnishingElement'
        ... )
        >>> print(len(furniture))
        2
    """
    # 1. Validate inputs
    if model is None:
        return []
    if not container_name or not element_type:
        return []

    # 2. Find the target spatial container
    target_container = None
    try:
        containers = model.by_type(container_type)
    except Exception:
        # If container_type is invalid, return empty
        return []

    for container in containers:
        # Use getattr to safely access attributes that might not exist
        # Handle None values gracefully
        c_name = getattr(container, 'Name', None)
        c_long_name = getattr(container, 'LongName', None)

        # Exact match logic for name or longname
        if c_name == container_name or c_long_name == container_name:
            target_container = container
            break

    # If container is not found, return empty list
    if target_container is None:
        return []

    # 3. Retrieve contained elements using IfcOpenShell utility
    # This abstracts the traversal of IfcRelContainedInSpatialStructure
    try:
        all_contained_elements = ifcopenshell.util.element.get_contained(target_container)
    except Exception:
        # Fallback if utility fails or element is not a spatial structure element
        return []

    # 4. Filter by the requested element type
    matching_elements = []
    for element in all_contained_elements:
        if element.is_a(element_type):
            matching_elements.append(element)

    return matching_elements