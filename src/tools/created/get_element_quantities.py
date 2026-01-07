import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Union, Optional

def get_element_quantities(
    model: ifcopenshell.file,
    ifc_class: str,
    quantity_names: Union[str, List[str]],
    quantity_set_name: Optional[str] = None,
    element_name_attribute: str = 'LongName',
    name_pattern: Optional[Union[str, List[str]]] = None,
    storey_name: Optional[str] = None,
    element_ids: Optional[List[Union[str, int]]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves specific quantity values for elements of a given IFC class.

    This function abstracts the traversal of the `IsDefinedBy` relationship to locate
    `IfcElementQuantity` sets and extract values from specific quantities. It handles
    polymorphic value attributes like `AreaValue`, `VolumeValue`, `LengthValue`, etc.

    Args:
        model: The opened IFC model.
        ifc_class: The IFC element class to query (e.g., 'IfcSpace', 'IfcWall').
        quantity_names: The name of the quantity or list of names to extract 
            (e.g., 'FloorArea', 'Height').
        quantity_set_name: The name of the `IfcElementQuantity` set to search within 
            (e.g., 'GSA Space Areas', 'BaseQuantities'). If None, searches all quantity sets.
        element_name_attribute: The attribute on the element to use as the 'Name' in the output. 
            Defaults to 'LongName', falling back to 'Name'.
        name_pattern: Optional string or list of strings to filter elements by name. 
            Matching is case-insensitive and checks for substrings. If None, no name filtering is applied.
        storey_name: Optional name of the building storey to filter elements by. 
            If provided, only elements spatially contained within the matching `IfcBuildingStorey` 
            will be returned. Uses `ifcopenshell.util.element.get_container` to verify containment,
            with fallback to `Decomposes` relationship traversal for compatibility.
        element_ids: Optional list of element IDs (as strings or integers) to retrieve quantities for. 
            If provided, only elements matching these IDs will be processed. This enables efficient 
            targeted retrieval when elements have already been filtered (e.g., by storey). 
            If None, all instances of `ifc_class` are processed (default behavior).

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary contains the 'id', 
            'Name' (or specified attribute), and the requested quantity values 
            (keys match the `quantity_names`). 
            Returns an empty list if no matches are found.

    Example usage:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Get all wall quantities
        >>> results = get_element_quantities(model, 'IfcWall', ['Length', 'Width', 'Height'])
        
        >>> # Get quantities for walls with 'Int' in the name (e.g. Interior)
        >>> interior_results = get_element_quantities(
        ...     model, 'IfcWall', 
        ...     quantity_names=['Length', 'Width'], 
        ...     name_pattern='Int'
        ... )
        
        >>> # Get floor areas of all spaces on Level 1
        >>> level1_spaces = get_element_quantities(
        ...     model, 'IfcSpace',
        ...     quantity_names=['NetFloorArea'],
        ...     storey_name='Level 1'
        ... )
        
        >>> # Get quantities for specific elements by ID (optimized workflow)
        >>> results = get_element_quantities(
        ...     model, 'IfcSpace',
        ...     quantity_names=['NetFloorArea', 'GrossFloorArea'],
        ...     element_ids=[123, 456, 789]
        ... )
    """
    if isinstance(quantity_names, str):
        quantity_names = [quantity_names]
    
    results: List[Dict[str, Any]] = []
    elements = []
    
    # Determine how to get elements: by ID list or by class type
    if element_ids is not None:
        # Get specific elements by their IDs
        for elem_id in element_ids:
            try:
                # Convert string ID to integer if necessary
                id_int = int(elem_id) if isinstance(elem_id, str) else elem_id
                element = model.by_id(id_int)
                
                # Verify the element is of the correct class
                if element and element.is_a(ifc_class):
                    elements.append(element)
            except Exception:
                # Skip invalid IDs silently
                continue
    else:
        # Default behavior: get all elements of the class
        try:
            elements = model.by_type(ifc_class)
        except Exception:
            return []
    
    for element in elements:
        # Filter by storey if specified
        if storey_name is not None:
            storey_match = False
            
            # Method 1: Try using get_container utility (as per requirement)
            try:
                container = ifcopenshell.util.element.get_container(element)
                if container is not None and container.is_a('IfcBuildingStorey'):
                    if container.Name == storey_name:
                        storey_match = True
            except Exception:
                pass
            
            # Method 2: Fallback to Decomposes relationship if get_container failed or didn't match
            if not storey_match:
                if hasattr(element, 'Decomposes'):
                    for rel in element.Decomposes:
                        if hasattr(rel, 'RelatingObject'):
                            container = rel.RelatingObject
                            if container.is_a() == 'IfcBuildingStorey' and container.Name == storey_name:
                                storey_match = True
                                break
            
            if not storey_match:
                continue

        # Extract Element Name
        el_name: str = "Unknown"
        try:
            el_name = getattr(element, element_name_attribute, None)
            if el_name is None:
                el_name = getattr(element, 'Name', None)
            if el_name is None:
                el_name = str(element.id())
        except Exception:
            el_name = str(element.id())

        # Apply Name Filter
        if name_pattern:
            current_name = str(el_name) if el_name is not None else ""
            patterns = [name_pattern] if isinstance(name_pattern, str) else name_pattern
            match_found = any(p.lower() in current_name.lower() for p in patterns)
            if not match_found:
                continue

        element_data: Dict[str, Any] = {
            'id': element.id(),
            'Name': el_name
        }
        
        quantity_found = False

        # Traverse IsDefinedBy relationships
        if not hasattr(element, 'IsDefinedBy'):
            continue
            
        for rel in element.IsDefinedBy:
            try:
                if not hasattr(rel, 'RelatingPropertyDefinition'):
                    continue
                    
                prop_def = rel.RelatingPropertyDefinition
                
                if prop_def.is_a('IfcElementQuantity'):
                    if quantity_set_name and prop_def.Name != quantity_set_name:
                        continue
                    
                    for quantity in prop_def.Quantities:
                        if quantity.Name in quantity_names:
                            val = None
                            if hasattr(quantity, 'AreaValue'):
                                val = quantity.AreaValue
                            elif hasattr(quantity, 'VolumeValue'):
                                val = quantity.VolumeValue
                            elif hasattr(quantity, 'LengthValue'):
                                val = quantity.LengthValue
                            elif hasattr(quantity, 'CountValue'):
                                val = quantity.CountValue
                            elif hasattr(quantity, 'WeightValue'):
                                val = quantity.WeightValue
                            elif hasattr(quantity, 'TimeValue'):
                                val = quantity.TimeValue
                            
                            if val is not None:
                                element_data[quantity.Name] = val
                                quantity_found = True
            except Exception:
                continue
        
        if quantity_found:
            results.append(element_data)
            
    return results