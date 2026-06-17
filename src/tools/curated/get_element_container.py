import ifcopenshell
from typing import Optional

def get_element_container(
    model: ifcopenshell.file, 
    element: ifcopenshell.entity_instance, 
    container_type: str = 'IfcBuildingStorey'
) -> Optional[ifcopenshell.entity_instance]:
    """
    Retrieves the parent spatial structure (e.g., IfcBuildingStorey, IfcBuilding) 
    that contains a specific IFC element. This function navigates spatial 
    decomposition relationships (IfcRelContainedInSpatialStructure and 
    IfcRelAggregates) to find the element's container.

    Args:
        model: The IFC model instance.
        element: The IFC element to analyze (e.g., IfcSpace, IfcWall).
        container_type: The IFC type of the container to find 
            (e.g., 'IfcBuildingStorey', 'IfcBuilding'). 
            Defaults to 'IfcBuildingStorey'.

    Returns:
        The found container entity (ifcopenshell.entity_instance), or None if not found.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> spaces = model.by_type('IfcSpace')
        >>> if spaces:
        ...     storey = get_element_container(model, spaces[0], 'IfcBuildingStorey')
        ...     if storey:
        ...         print(storey.Name)
    """
    
    # 1. Check Containment (Physical Element -> Spatial Element)
    # Used for elements like IfcWall, IfcDoor contained in IfcSpace or IfcBuildingStorey
    try:
        if hasattr(element, 'ContainedInStructure'):
            for rel in element.ContainedInStructure:
                if rel and rel.is_a('IfcRelContainedInSpatialStructure'):
                    container = rel.RelatingStructure
                    if container and container.is_a(container_type):
                        return container
    except AttributeError:
        # Element might not have this inverse attribute
        pass
    
    # 2. Check Decomposition (Spatial Element -> Spatial Element)
    # Used for elements like IfcSpace contained in IfcBuildingStorey
    try:
        if hasattr(element, 'Decomposes'):
            for rel in element.Decomposes:
                if rel and rel.is_a('IfcRelAggregates'):
                    container = rel.RelatingObject
                    if container and container.is_a(container_type):
                        return container
    except AttributeError:
        # Element might not have this inverse attribute
        pass
        
    return None