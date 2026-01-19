import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Set, Union, Callable, Literal


def _get_empty_result(return_type: str) -> Union[Dict[str, Any], Set[Any], List[Dict[str, Any]], float]:
    """Helper to return empty structures based on return_type."""
    if return_type == 'stats':
        return {
            'values': [], 'count_total': 0, 'count_found': 0,
            'count_missing': 0, 'min': None, 'max': None,
            'avg': None, 'sum': None
        }
    elif return_type == 'unique':
        return set()
    elif return_type == 'all':
        return []
    elif return_type == 'proportion':
        return 0.0
    elif return_type == 'distribution':
        return {
            'count_total': 0, 'count_found': 0, 'count_missing': 0, 'distribution': {}
        }
    return {}


def _robust_value_extractor(entity) -> Any:
    """Extracts the actual Python value from an IFC property or quantity instance.
    
    Handles IfcPropertySingleValue (via NominalValue.wrappedValue) and 
    IfcPhysicalSimpleQuantity subtypes (via LengthValue, AreaValue, etc.).
    """
    if entity is None:
        return None
    
    # Handle IfcPropertySingleValue (and similar properties)
    # NominalValue contains the wrapper (e.g., IfcLengthMeasure)
    if hasattr(entity, 'NominalValue'):
        nom = entity.NominalValue
        if hasattr(nom, 'wrappedValue'):
            return nom.wrappedValue
        return nom
    
    # Handle IfcPhysicalSimpleQuantity subtypes
    # Common attributes: LengthValue, AreaValue, VolumeValue, CountValue, WeightValue, TimeValue
    quantity_attrs = [
        'LengthValue', 'AreaValue', 'VolumeValue', 
        'CountValue', 'WeightValue', 'TimeValue'
    ]
    for attr in quantity_attrs:
        if hasattr(entity, attr):
            val = getattr(entity, attr)
            # Quantities might also be wrapped in some schemas
            if hasattr(val, 'wrappedValue'):
                return val.wrappedValue
            return val
            
    return None


def get_element_property_stats(
    model: ifcopenshell.file,
    ifc_type: Union[str, List[str]],
    prop_name: str,
    pset_name: Optional[str] = None,
    quantity_name: Optional[str] = None,
    return_type: str = 'stats',
    return_elements: bool = False,
    name_matching: str = 'exact',
    filter_func: Optional[Callable[[ifcopenshell.entity_instance], bool]] = None,
    target_value: Optional[Any] = None,
    include_attributes: List[str] = [],
    sort_by_value: Optional[Literal['asc', 'desc']] = None,
    limit: Optional[int] = None,
    storey_name: Optional[str] = None,
    filter_pset_name: Optional[str] = None,
    filter_prop_name: Optional[str] = None,
    filter_value: Any = None,
    element_identifier: Optional[str] = None,
    identifier_attribute: str = 'Name',
    return_single_value: bool = False,
    aggregation: Optional[Literal['sum', 'count', 'mean', 'min', 'max']] = None,
    search_paths: Optional[List[Dict[str, str]]] = None
) -> Union[Dict[str, Any], Set[Any], List[Dict[str, Any]], float, Any]:
    """
    Extracts a specific property from instances of a given IFC element type, optionally filtered 
    by a custom function, spatial containment, or a specific property value. Supports batch 
    processing of multiple IFC types.

    This function abstracts the complexity of looking up properties across different IFC definitions
    (direct attributes, property sets, and element quantities) and allows flexible return formats.

    Args:
        model (ifcopenshell.file): The loaded IFC model instance.
        ifc_type (Union[str, List[str]]): The IFC class name to query (e.g., 'IfcWindow', 'IfcWall'). 
            Can be a single string or a list of strings for batch processing.
        prop_name (str): The name of the property to search for (e.g., 'Width', 'Height', 'Area').
        pset_name (str, optional): Specific PropertySet name to filter by.
            If None, searches all property sets and quantities.
        quantity_name (str, optional): Specific Quantity name to search for within Quantity sets.
            If provided, this acts as an alternative key to search for in addition to prop_name.
        return_type (str, optional): Format of the return value. Defaults to 'stats'.
            - 'stats': Returns statistical dictionary (min, max, avg, sum, values list, counts).
            - 'unique': Returns a set of unique values found across all elements.
            - 'all': Returns a list of dictionaries with element details and values.
            - 'proportion': Returns a float representing the ratio of the sum of property values 
              to the total count of elements (useful for boolean 0/1 properties), or the ratio
              of elements matching `target_value` if provided.
            - 'distribution': Returns a dictionary with count_total, count_found, count_missing,
              and a 'distribution' key mapping each unique value to its count and percentage (2 decimal places).
        return_elements (bool, optional): If True, returns a list of element dictionaries with 
            property values and attributes (same as return_type='all'). This provides a more 
            intuitive alias for users who want element-level data. Default is False.
            When True, this effectively sets return_type='all' regardless of the return_type parameter.
        name_matching (str, optional): Property name matching strategy. Defaults to 'exact'.
            - 'exact': Property name must exactly match prop_name (case-sensitive).
            - 'contains': Property name must contain prop_name as a substring.
            - 'startswith': Property name must start with prop_name.
        filter_func (Callable[[ifcopenshell.entity_instance], bool], optional): A function to filter elements.
            If provided, only elements for which this function returns True are processed.
            Example: lambda e: e.PredefinedType == 'FLOOR'
        target_value (Any, optional): A specific value to match against for calculating proportion.
            If provided, proportion is calculated as (count of elements with this value) / (total count).
            If None (default), proportion is calculated as (sum of values) / (total count).
        include_attributes (List[str], optional): A list of additional element attributes to include 
            in the returned dictionaries when return_type='all' or return_elements=True. Defaults to [].
            Example: ['LongName', 'Description', 'ObjectType']
        sort_by_value (Literal['asc', 'desc'], optional): Sorts the returned list of elements by their 
            extracted property value when return_type='all' or return_elements=True. 'desc' is useful for finding largest/highest values.
            Defaults to None (no sorting).
        limit (int, optional): When return_type='all' or return_elements=True, returns only the top N results from the 
            (optionally sorted) list. Defaults to None (return all results).
        storey_name (str, optional): Specific building storey name to filter elements by.
            Elements are filtered to only include those spatially contained within a
            storey matching this name. Uses multiple relationship strategies including
            IfcRelDecomposes (IsDecomposedBy) and IfcRelContainedInSpatialStructure (ContainsElements),
            with a fallback to element-container lookups. Defaults to None (all storeys).
        filter_pset_name (str, optional): PropertySet name to search for the filter property.
            Used in conjunction with filter_prop_name and filter_value.
        filter_prop_name (str, optional): Property name to use as a filter condition.
            If provided, only elements where this property matches filter_value are processed.
        filter_value (Any, optional): The value that filter_prop_name must match for the element to be included.
        element_identifier (str, optional): If provided, filters elements to those matching this 
            identifier value (e.g., 'A203'). When set, automatically applies a filter matching the 
            specified identifier_attribute. Defaults to None.
        identifier_attribute (str, optional): The attribute to match against element_identifier 
            (e.g., 'Name', 'LongName', 'GlobalId'). Default is 'Name'.
        return_single_value (bool, optional): If True, and exactly one element matches the filter, 
            returns only the property value directly (or None if not found) instead of the complex 
            stats/unique structure. Useful for simple property lookups on specific elements. 
            Defaults to False.
        aggregation (Literal['sum', 'count', 'mean', 'min', 'max'], optional): If provided, returns 
            a single aggregated value directly, bypassing the standard return_type structure. 
            The function will internally use return_type='all' to retrieve data and compute the 
            requested aggregation. Cannot be used with return_single_value=True.
            - 'sum': Sum of all property values (numeric only).
            - 'count': Count of elements with the property.
            - 'mean': Average (mean) of all property values (numeric only).
            - 'min': Minimum property value.
            - 'max': Maximum property value.
        search_paths (List[Dict[str, str]], optional): A list of dictionaries defining specific lookup paths 
            to try in priority order. Each dictionary should specify the source set and the property/quantity name. 
            This enables searching in non-standard or localized property sets.
            
            If provided, this parameter is used as the primary extraction method. If a value is not found via 
            search_paths, the function falls back to the standard `prop_name`/`pset_name` logic.
            
            Keys in dictionary:
                - 'pset_name' (str): Name of the PropertySet (e.g., 'Abmessungen').
                - 'prop_name' (str): Name of the Property within the PSet (e.g., 'Lichte Höhe').
            OR
                - 'qset_name' (str): Name of the QuantitySet (e.g., 'Qto_SpaceBaseQuantities').
                - 'quantity_name' (str): Name of the Quantity within the QSet (e.g., 'Height').
                
            Example:
                [
                    {'pset_name': 'Abmessungen', 'prop_name': 'Lichte Höhe'},
                    {'qset_name': 'Qto_SpaceBaseQuantities', 'quantity_name': 'Height'}
                ]

    Returns:
        Union[Dict[str, Any], Set[Any], List[Dict[str, Any]], float, Any]:
            If 'ifc_type' is a list (batch mode): Returns a dictionary keyed by IFC type name, 
            where values are the results of the analysis for that type.
            
            If 'ifc_type' is a string (single mode): Returns the result directly.
            
            - If 'stats': A dictionary with keys 'values', 'count_total', 'count_found',
              'count_missing', 'min', 'max', 'avg', 'sum'.
            - If 'unique': A set of unique values.
            - If 'all': A list of dictionaries, each with 'element_id', 'element_name', 'value',
              and any additional attributes specified in include_attributes.
            - If 'proportion': A float between 0.0 and 1.0.
            - If 'distribution': A dictionary with keys 'count_total', 'count_found', 'count_missing',
              and 'distribution' (a dict of values -> {count, percentage}).
            - If return_elements=True: Same as 'all' - a list of element dictionaries.
            - If return_single_value=True: The property value directly, or None if not found.
            - If aggregation is specified: The single aggregated value (float for numeric operations,
              int for count, or Any for min/max).
    """
    # Handle return_elements parameter - it maps to return_type='all'
    if return_elements:
        return_type = 'all'
    
    # Input validation for common args
    if model is None:
        raise ValueError("Model cannot be None")
    if not prop_name or not isinstance(prop_name, str):
        raise ValueError("prop_name must be a non-empty string")
    
    valid_return_types = ['stats', 'unique', 'all', 'proportion', 'distribution']
    if return_type not in valid_return_types:
        raise ValueError(f"return_type must be one of {valid_return_types}")
    if name_matching not in ['exact', 'contains', 'startswith']:
        raise ValueError("name_matching must be one of 'exact', 'contains', 'startswith'")
    if sort_by_value is not None and sort_by_value not in ['asc', 'desc']:
        raise ValueError("sort_by_value must be None, 'asc', or 'desc'")
    if limit is not None and (not isinstance(limit, int) or limit < 1):
        raise ValueError("limit must be a positive integer or None")
    
    if aggregation is not None:
        valid_aggregations = ['sum', 'count', 'mean', 'min', 'max']
        if aggregation not in valid_aggregations:
            raise ValueError(f"aggregation must be one of {valid_aggregations} or None")
        if return_single_value:
            raise ValueError("Cannot use both 'aggregation' and 'return_single_value' parameters")

    # Helper to clean wrapped values (e.g., IfcLabel, IfcReal) for standard lookup path
    def _clean_value(val: Any) -> Any:
        if hasattr(val, 'wrappedValue'):
            return val.wrappedValue
        return val

    def _extract_via_search_paths(elem: ifcopenshell.entity_instance, paths: List[Dict[str, str]]) -> Optional[Any]:
        """Attempts to extract a value from an element using the provided search paths."""
        if not hasattr(elem, 'IsDefinedBy'):
            return None
            
        for path in paths:
            target_pset = path.get('pset_name')
            target_prop = path.get('prop_name')
            target_qset = path.get('qset_name')
            target_qty = path.get('quantity_name')
            
            # Validate path structure
            is_prop_path = target_pset and target_prop
            is_qty_path = target_qset and target_qty
            
            if not (is_prop_path or is_qty_path):
                continue 
                
            for rel in elem.IsDefinedBy:
                if not hasattr(rel, 'RelatingPropertyDefinition'):
                    continue
                    
                definition = rel.RelatingPropertyDefinition
                if definition is None:
                    continue

                # Handle Property Sets
                if is_prop_path and definition.is_a('IfcPropertySet'):
                    if definition.Name == target_pset:
                        if hasattr(definition, 'HasProperties'):
                            for prop in definition.HasProperties:
                                if prop.Name == target_prop:
                                    return _robust_value_extractor(prop)
                                    
                # Handle Quantity Sets
                elif is_qty_path and definition.is_a('IfcElementQuantity'):
                    if definition.Name == target_qset:
                        if hasattr(definition, 'Quantities'):
                            for qty in definition.Quantities:
                                if qty.Name == target_qty:
                                    return _robust_value_extractor(qty)
        return None

    # Internal helper to process a SINGLE type (avoid code duplication)
    def _process_single_type(current_type: str) -> Union[Dict[str, Any], Set[Any], List[Dict[str, Any]], float, Any]:
        """Core logic for processing a single IFC type."""
        
        # Retrieve elements
        try:
            all_elements = model.by_type(current_type)
        except RuntimeError:
            if return_single_value or aggregation is not None:
                return None if return_single_value else (0 if aggregation == 'count' else (0.0 if aggregation in ['sum', 'mean'] else None))
            return _get_empty_result(return_type)
            
        if not all_elements:
            if return_single_value or aggregation is not None:
                return None if return_single_value else (0 if aggregation == 'count' else (0.0 if aggregation in ['sum', 'mean'] else None))
            return _get_empty_result(return_type)

        # --- Apply Storey Filtering ---
        if storey_name is not None:
            storey_filtered_elements = []
            skipped_storey_errors = 0
            
            target_storey = None
            try:
                for storey in model.by_type('IfcBuildingStorey'):
                    if hasattr(storey, 'Name') and storey.Name == storey_name:
                        target_storey = storey
                        break
            except (AttributeError, RuntimeError):
                pass
            
            found_elements_top_down = False
            if target_storey is not None:
                if hasattr(target_storey, 'IsDecomposedBy'):
                    try:
                        for rel in target_storey.IsDecomposedBy:
                            if rel.is_a('IfcRelDecomposes'):
                                for related_obj in rel.RelatedObjects:
                                    if related_obj.is_a(current_type):
                                        storey_filtered_elements.append(related_obj)
                    except (AttributeError, RuntimeError):
                        pass
                
                if hasattr(target_storey, 'ContainsElements'):
                    try:
                        for rel in target_storey.ContainsElements:
                            if rel.is_a('IfcRelContainedInSpatialStructure'):
                                for related_elem in rel.RelatedElements:
                                    if related_elem.is_a(current_type):
                                        storey_filtered_elements.append(related_elem)
                    except (AttributeError, RuntimeError):
                        pass
                
                if storey_filtered_elements:
                    found_elements_top_down = True
            
            if not found_elements_top_down:
                for elem in all_elements:
                    try:
                        container = ifcopenshell.util.element.get_container(elem)
                        if container and container.is_a('IfcBuildingStorey') and container.Name == storey_name:
                            storey_filtered_elements.append(elem)
                    except (AttributeError, RuntimeError):
                        skipped_storey_errors += 1
                        continue
            
            if skipped_storey_errors > 0:
                print(f"Warning: Skipped {skipped_storey_errors} elements due to storey container access errors for {current_type}.")
            
            unique_elements_map = {e.id(): e for e in storey_filtered_elements}
            all_elements = list(unique_elements_map.values())
            
            if not all_elements:
                if return_single_value or aggregation is not None:
                    return None if return_single_value else (0 if aggregation == 'count' else (0.0 if aggregation in ['sum', 'mean'] else None))
                return _get_empty_result(return_type)

        # --- Apply Custom Function Filtering ---
        elements: List[ifcopenshell.entity_instance] = []
        skipped_filter_errors = 0
        
        if filter_func is not None:
            for elem in all_elements:
                try:
                    if filter_func(elem):
                        elements.append(elem)
                except (AttributeError, TypeError, KeyError):
                    skipped_filter_errors += 1
            if skipped_filter_errors > 0:
                 print(f"Warning: Skipped {skipped_filter_errors} elements due to filter_func errors for {current_type}.")
        else:
            elements = all_elements

        if not elements:
            if return_single_value or aggregation is not None:
                return None if return_single_value else (0 if aggregation == 'count' else (0.0 if aggregation in ['sum', 'mean'] else None))
            return _get_empty_result(return_type)

        # --- Property Extraction ---
        extracted_data: List[tuple] = []
        filter_skipped = 0
        missing_count = 0

        search_keys = [prop_name]
        if quantity_name and quantity_name not in search_keys:
            search_keys.append(quantity_name)

        def is_match(prop_key: str, search_key: str) -> bool:
            if name_matching == 'exact': return prop_key == search_key
            elif name_matching == 'contains': return search_key in prop_key
            elif name_matching == 'startswith': return prop_key.startswith(search_key)
            return False

        # --- Identifier Filtering ---
        effective_filter_func = filter_func
        if element_identifier is not None:
            def identifier_filter(elem):
                try:
                    attr_val = getattr(elem, identifier_attribute, None)
                    return str(attr_val) == str(element_identifier)
                except (AttributeError, TypeError):
                    return False
            
            if filter_func:
                def combined(elem): return identifier_filter(elem) and filter_func(elem)
                effective_filter_func = combined
            else:
                effective_filter_func = identifier_filter

        if effective_filter_func != filter_func:
            elements = [e for e in all_elements if effective_filter_func(e)]
            if not elements:
                return _get_empty_result(return_type) if not (return_single_value or aggregation) else (None if return_single_value else 0)

        for elem in elements:
            # Property-based Filter
            if filter_prop_name is not None:
                filter_val = None
                try:
                    psets = ifcopenshell.util.element.get_psets(elem)
                    found_filter = False
                    if psets:
                        keys = [filter_pset_name] if filter_pset_name else psets.keys()
                        for pk in keys:
                            if pk in psets:
                                for k in psets[pk].keys():
                                    if is_match(k, filter_prop_name):
                                        filter_val = _clean_value(psets[pk][k])
                                        found_filter = True
                                        break
                            if found_filter: break
                    if not filter_val and filter_pset_name is None and hasattr(elem, filter_prop_name):
                         filter_val = _clean_value(getattr(elem, filter_prop_name))
                    
                    if filter_val != filter_value:
                        filter_skipped += 1
                        continue
                except (AttributeError, RuntimeError):
                    filter_skipped += 1
                    continue

            # Target Extraction
            raw_value: Any = None
            found = False
            
            # Priority 1: Use search_paths if provided
            if search_paths:
                raw_value = _extract_via_search_paths(elem, search_paths)
                if raw_value is not None:
                    found = True
            
            # Priority 2: Fallback to standard logic if not found
            if not found:
                try:
                    elem_psets = ifcopenshell.util.element.get_psets(elem)
                except (AttributeError, RuntimeError):
                    elem_psets = {}

                # Direct Attrs
                if pset_name is None and name_matching == 'exact':
                    for attr in [prop_name, f"Overall{prop_name}"]:
                        if hasattr(elem, attr):
                            try:
                                val = getattr(elem, attr)
                                if val is not None:
                                    raw_value = _clean_value(val)
                                    found = True
                                    break
                            except (AttributeError, RuntimeError): pass
                
                # Psets
                if not found and elem_psets:
                    keys_to_search = [pset_name] if pset_name else elem_psets.keys()
                    for pset_key in keys_to_search:
                        if pset_key not in elem_psets: continue
                        props = elem_psets[pset_key]
                        for prop_key in props.keys():
                            for search_key in search_keys:
                                if is_match(prop_key, search_key):
                                    try:
                                        val = props[prop_key]
                                        if val is not None:
                                            raw_value = _clean_value(val)
                                            found = True
                                            break
                                    except (AttributeError, RuntimeError): pass
                            if found: break
                        if found: break
            
            if found:
                extracted_data.append((elem, raw_value))
            else:
                missing_count += 1

        # --- Single Value Return ---
        if return_single_value:
            if len(extracted_data) == 0: return None
            if len(extracted_data) == 1: return extracted_data[0][1]
            print(f"Warning: {len(extracted_data)} elements matched filter for single value lookup in {current_type}. Returning first.")
            return extracted_data[0][1]

        base_count = len(elements) - filter_skipped
        
        # --- Aggregation ---
        if aggregation is not None:
            values = [val for _, val in extracted_data]
            if not values:
                if aggregation == 'count': return 0
                elif aggregation in ['sum', 'mean']: return 0.0
                else: return None
            
            if aggregation == 'count': return len(values)
            elif aggregation == 'sum': return sum(float(v) for v in values if isinstance(v, (int, float)))
            elif aggregation == 'mean': 
                nums = [float(v) for v in values if isinstance(v, (int, float))]
                return sum(nums)/len(nums) if nums else 0.0
            elif aggregation == 'min': return min(values)
            elif aggregation == 'max': return max(values)

        # --- Return Types ---
        if return_type == 'all':
            result_list = []
            for elem, val in extracted_data:
                d = {'element_id': elem.id(), 'element_name': elem.Name if hasattr(elem, 'Name') else str(elem.id()), 'value': val}
                if include_attributes:
                    for attr in include_attributes:
                        try:
                            v = getattr(elem, attr, None)
                            d[attr] = _clean_value(v) if hasattr(v, 'wrappedValue') else v
                        except: d[attr] = None
                result_list.append(d)
            
            if sort_by_value is not None:
                try:
                    rev = (sort_by_value == 'desc')
                    result_list.sort(key=lambda x: x['value'] if x['value'] is not None else float('-inf' if not rev else float('inf')), reverse=rev)
                except TypeError: pass
            if limit is not None: result_list = result_list[:limit]
            return result_list

        elif return_type == 'unique':
            return {val for _, val in extracted_data}

        elif return_type == 'proportion':
            if base_count == 0: return 0.0
            if target_value is not None:
                match = sum(1 for _, v in extracted_data if v == target_value)
                return match / base_count
            else:
                nums = [float(v) for _, v in extracted_data if isinstance(v, (int, float))]
                return sum(nums) / base_count if nums else 0.0

        elif return_type == 'distribution':
            dist_map = {}
            for _, val in extracted_data:
                try: dist_map[val] = dist_map.get(val, 0) + 1
                except TypeError: dist_map[str(val)] = dist_map.get(str(val), 0) + 1
            
            dist_final = {}
            for k, v in dist_map.items():
                dist_final[k] = {'count': v, 'percentage': round((v/len(extracted_data))*100, 2) if extracted_data else 0}
            
            return {'count_total': base_count, 'count_found': len(extracted_data), 'count_missing': missing_count, 'distribution': dist_final}

        elif return_type == 'stats':
            nums = [float(v) for _, v in extracted_data if isinstance(v, (int, float))]
            return {
                'values': nums, 'count_total': base_count, 'count_found': len(extracted_data),
                'count_missing': missing_count, 'min': min(nums) if nums else None,
                'max': max(nums) if nums else None, 'avg': sum(nums)/len(nums) if nums else None,
                'sum': sum(nums) if nums else None
            }
        return _get_empty_result(return_type)

    # --- MAIN DISPATCHER ---
    
    # Check if we are in batch mode
    if isinstance(ifc_type, list):
        results = {}
        for t in ifc_type:
            if not isinstance(t, str):
                print(f"Warning: Skipping non-string type in list: {t}")
                continue
            try:
                results[t] = _process_single_type(t)
            except Exception as e:
                print(f"Warning: Unexpected error processing type '{t}': {e}")
                results[t] = _get_empty_result(return_type) 
        return results
    else:
        # Single mode
        if not ifc_type or not isinstance(ifc_type, str):
             raise ValueError("ifc_type must be a non-empty string or list of strings")
        return _process_single_type(ifc_type)
