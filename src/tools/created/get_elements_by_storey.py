import ifcopenshell
from typing import List

def get_elements_by_storey(model: ifcopenshell.file, ifc_class: str, storey_name: str) -> List[ifcopenshell.entity_instance]:
    """
    Retrieves all elements of a specific IFC class that are directly contained within 
    a given building storey.

    This function abstracts the traversal of spatial relationships. It checks both
    `ContainedInStructure` (spatial containment) and `Decomposes` (aggregation) 
    relationships to ensure robustness across different modeling standards 
    (e.g., some models use aggregation for Spaces, others use containment).

    Args:
        model (ifcopenshell.file): The opened IFC model.
        ifc_class (str): The IFC class to filter (e.g., 'IfcBuildingElementProxy', 'IfcWindow').
        storey_name (str): The Name of the target storey (e.g., 'B01_OKRD').

    Returns:
        List[ifcopenshell.entity_instance]: A list of elements of the specified class found in the 
            specified storey. Returns an empty list if the storey or elements are not found.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> elements = get_elements_by_storey(model, 'IfcWindow', '01 - Entry Level')
        >>> print(len(elements))
        5
    """
    try:
        # Retrieve all elements of the requested class
        elements = model.by_type(ifc_class)
        result = []

        for element in elements:
            found_in_storey = False

            # Check 1: Spatial Containment (IfcRelContainedInSpatialStructure)
            # This is the standard way physical elements (Walls, Windows) relate to Storeys.
            if hasattr(element, 'ContainedInStructure') and element.ContainedInStructure:
                for rel in element.ContainedInStructure:
                    if rel.is_a('IfcRelContainedInSpatialStructure'):
                        storey = rel.RelatingStructure
                        if storey and storey.is_a('IfcBuildingStorey'):
                            if storey.Name == storey_name:
                                result.append(element)
                                found_in_storey = True
                                break
            
            if found_in_storey:
                continue

            # Check 2: Aggregation (IfcRelAggregates / Decomposes)
            # This is sometimes used for Spatial Elements (IfcSpace) depending on the model.
            if not found_in_storey and hasattr(element, 'Decomposes') and element.Decomposes:
                for rel in element.Decomposes:
                    # IfcRelAggregates and IfcRelNests inherit from IfcRelDecomposes
                    if rel.is_a('IfcRelAggregates') or rel.is_a('IfcRelNests'):
                        parent = rel.RelatingObject
                        if parent and parent.is_a('IfcBuildingStorey'):
                            if parent.Name == storey_name:
                                result.append(element)
                                break
        
        return result
    except Exception as e:
        print(f"Error in get_elements_by_storey: {e}")
        return []