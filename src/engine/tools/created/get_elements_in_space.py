
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import List, Union

def get_elements_in_space(space_element: ifcopenshell.entity_instance) -> List[ifcopenshell.entity_instance]:
    """
    Retrieves all elements contained within a specific space or spatial structure element.
    
    This function is a wrapper around ifcopenshell.util.element.get_contained() to provide
    a more intuitive name for finding elements within a space. It returns all elements that
    are directly contained in the specified space, such as furniture, equipment, or fixtures.
    
    Args:
        space_element (ifcopenshell.entity_instance): An IFC space or spatial structure 
            element (IfcSpace, IfcBuildingStorey, etc.) to find contained elements within.
            
    Returns:
        List[ifcopenshell.entity_instance]: A list of elements contained within the space.
            This may include furniture, equipment, fixtures, and other elements that are
            directly contained in the space.
            
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open("model.ifc")
        >>> space = model.by_type("IfcSpace")[0]
        >>> elements = get_elements_in_space(space)
        >>> print([e.Name for e in elements])
        
    Note:
        This function finds elements that are directly contained in a space. For elements
        that reference a space (like multistorey columns), use 
        ifcopenshell.util.element.get_referenced_structures() instead.
    """
    return ifcopenshell.util.element.get_contained(space_element)
