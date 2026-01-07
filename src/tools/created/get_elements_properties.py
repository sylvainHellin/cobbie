import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Tuple

def get_elements_properties(
    model: ifcopenshell.file,
    ifc_class: str,
    property_queries: List[Tuple[str, str]],
    element_identifier: str = 'Name'
) -> List[Dict[str, Any]]:
    """
    Retrieves multiple properties for elements of a given IFC class and returns them in a unified tabular format.
    This function abstracts the logic of iterating through elements, extracting values from multiple 
    Property Sets, and joining them by the element identifier.

    Args:
        model (ifcopenshell.file): The opened IFC model.
        ifc_class (str): The IFC class to query (e.g., 'IfcWall', 'IfcWindow').
        property_queries (List[Tuple[str, str]]): A list of tuples where each tuple specifies 
                                                 (Pset_Name, Property_Name) to extract.
        element_identifier (str, optional): The attribute to use as the element key in the output. 
                                           Defaults to 'Name'.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, one per matching element. Each dictionary 
                              contains the element identifier and the values for all requested properties.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> queries = [('Pset_WallCommon', 'LoadBearing'), ('Pset_WallCommon', 'IsExternal')]
        >>> walls = get_elements_properties(model, 'IfcWall', queries)
        >>> for w in walls:
        ...     print(f"{w['Name']} - LoadBearing: {w['LoadBearing']}")
    """
    results = []
    # Iterate over all elements of the specified class
    elements = model.by_type(ifc_class)

    for element in elements:
        row = {}

        # 1. Extract Element Identifier (e.g., Name, GlobalId, ID)
        row[element_identifier] = getattr(element, element_identifier, None)

        # 2. Extract Properties
        try:
            # get_psets returns a dict: {'PsetName': {'PropName': Value}}
            psets = ifcopenshell.util.element.get_psets(element)
        except Exception:
            # If psets cannot be retrieved, fill with None for requested props
            for _, prop_name in property_queries:
                row[prop_name] = None
            results.append(row)
            continue

        # Retrieve each requested property
        for pset_name, prop_name in property_queries:
            # Safely navigate the nested dictionary structure
            # Returns None if pset or property is not found
            val = psets.get(pset_name, {}).get(prop_name)
            row[prop_name] = val

        results.append(row)

    return results