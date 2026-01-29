import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_stair_slab_connection(model: ifcopenshell.file) -> List[str]:
    """
    Check if all stairs in the IFC model are connected to slabs.

    A stair is considered 'connected to slabs' if it shares a spatial container
    (e.g., IfcBuildingStorey) with at least one IfcSlab element.

    Args:
        model: An opened IFC file object (ifcopenshell.file)

    Returns:
        List[str]: A list of IFC GUIDs of all stair elements that are NOT
                  connected to any slab. Returns empty list if all stairs
                  are properly connected.

    Raises:
        Exception: If there's an error accessing the IFC model data

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> violations = check_504_2_stair_slab_connection(model)
        >>> print(f"Violations: {violations}")
    """
    try:
        # Get all stairs in the model
        stairs = model.by_type('IfcStair')
        violations = []

        for stair in stairs:
            # Get the spatial container of the stair
            container = ifcopenshell.util.element.get_container(stair)

            # If stair has no container, it's a violation
            if container is None:
                violations.append(stair.GlobalId)
                continue

            # Get all elements in the same container
            container_elements = ifcopenshell.util.element.get_decomposition(container)

            # Check if there's at least one slab in the same container
            slabs_in_container = [e for e in container_elements if e.is_a() == 'IfcSlab']

            if len(slabs_in_container) == 0:
                violations.append(stair.GlobalId)

        return violations

    except Exception as e:
        raise Exception(f"Error checking stair-slab connection: {str(e)}")