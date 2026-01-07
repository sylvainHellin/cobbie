import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Union, Any

def get_distribution_by_attribute(
    model: ifcopenshell.file,
    ifc_class: Union[str, List[str]],
    attribute_name: str,
    include_null: bool = True,
    pset_name: Optional[str] = None,
    prop_name: Optional[str] = None,
    filter_pset_name: Optional[str] = None,
    filter_prop_name: Optional[str] = None,
    filter_prop_value: Optional[Any] = None
) -> Union[Dict[str, int], Dict[str, Dict[str, int]]]:
    """
    Calculates the distribution of elements for given IFC class(es) based on a specific
    instance attribute or a property from a Property Set (Pset).

    Args:
        model (ifcopenshell.file): The opened IFC model.
        ifc_class (Union[str, List[str]]): The IFC class(es) to analyze (e.g., 'IfcFooting', 'IfcWall').
            Can be a single class string or a list of class strings.
        attribute_name (str): The attribute name to group by (e.g., 'ObjectType', 'PredefinedType', 'Name')
            when not using Property Sets. This parameter is required but may be ignored if pset_name and
            prop_name are provided.
        include_null (bool, optional): If True, counts elements where the attribute or property is missing
            under 'No Value'. Defaults to True.
        pset_name (Optional[str], optional): The name of the Property Set containing the data.
            If provided along with prop_name, the function retrieves data from the Property Set instead of
            native attributes. Defaults to None.
        prop_name (Optional[str], optional): The name of the property within the Pset. Must be provided
            along with pset_name to use Property Set lookup. Defaults to None.
        filter_pset_name (Optional[str], optional): Property set name for pre-filtering elements. 
            When provided along with filter_prop_name and filter_prop_value, only elements matching 
            the property value will be included in the distribution analysis. Defaults to None.
        filter_prop_name (Optional[str], optional): Property name within the filter Pset for pre-filtering.
            Defaults to None.
        filter_prop_value (Optional[Any], optional): Property value to match for pre-filtering.
            Defaults to None.

    Returns:
        Union[Dict[str, int], Dict[str, Dict[str, int]]]: 
            - If `ifc_class` is a string, returns a dictionary where keys are attribute/property values 
              and values are counts of elements.
            - If `ifc_class` is a list, returns a dictionary where keys are IFC class names and values 
              are the distribution dictionaries for each class.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Single class usage (standard)
        >>> dist = get_distribution_by_attribute(model, 'IfcFooting', 'ObjectType')
        >>> print(dist)
        {'Footing Type A': 10, 'Footing Type B': 5}
        
        >>> # Multiple class usage (enhanced)
        >>> dists = get_distribution_by_attribute(
        ...     model, ['IfcWall', 'IfcColumn'], 'ObjectType'
        ... )
        >>> print(dists)
        {
            'IfcWall': {'Basic Wall: 300': 50, 'Basic Wall: 200': 20},
            'IfcColumn': {'Rectangular Column: 400x400': 10}
        }
        
        >>> # Pre-filtering usage: Get ObjectType of load-bearing walls
        >>> lb_wall_types = get_distribution_by_attribute(
        ...     model, 'IfcWall', 'ObjectType',
        ...     filter_pset_name='Pset_WallCommon',
        ...     filter_prop_name='LoadBearing',
        ...     filter_prop_value=True
        ... )
        >>> print(lb_wall_types)
        {'Basic Wall:Retaining - 300mm Concrete': 10, 'Basic Wall:CL_W1': 9}
    """
    # Normalize input to a list for unified processing
    is_single_class = isinstance(ifc_class, str)
    classes_to_process = [ifc_class] if is_single_class else ifc_class
    
    aggregated_results: Dict[str, Dict[str, int]] = {}

    # Determine if we're using Property Sets or native attributes for distribution
    use_pset = (pset_name is not None) and (prop_name is not None)
    
    # Determine if pre-filtering is enabled (all three filter params must be provided)
    use_filter = (filter_pset_name is not None and 
                  filter_prop_name is not None and 
                  filter_prop_value is not None)

    for current_class in classes_to_process:
        distribution: Dict[str, int] = {}
        
        try:
            elements = model.by_type(current_class)
        except Exception:
            aggregated_results[current_class] = {}
            continue

        for element in elements:
            # Apply pre-filter if enabled
            if use_filter:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    if filter_pset_name not in psets:
                        continue  # Element doesn't have the filter Pset, skip it
                    if filter_prop_name not in psets[filter_pset_name]:
                        continue  # Element doesn't have the filter property, skip it
                    # Check if the property value matches
                    if psets[filter_pset_name][filter_prop_name] != filter_prop_value:
                        continue  # Property value doesn't match, skip element
                except Exception:
                    continue  # Error reading filter properties, skip element
            
            # Get the value for distribution
            value = None
            
            if use_pset:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    if pset_name in psets and prop_name in psets[pset_name]:
                        value = psets[pset_name][prop_name]
                except Exception:
                    value = None
            else:
                # Use native attribute
                value = getattr(element, attribute_name, None)
            
            if value is None:
                if include_null:
                    key = "No Value"
                    distribution[key] = distribution.get(key, 0) + 1
            else:
                # Convert value to string to ensure consistent dictionary keys
                key = str(value)
                distribution[key] = distribution.get(key, 0) + 1
        
        aggregated_results[current_class] = distribution

    if is_single_class:
        return aggregated_results[ifc_class] # type: ignore
    else:
        return aggregated_results