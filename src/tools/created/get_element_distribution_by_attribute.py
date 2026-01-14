import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Callable, Literal
import re

def get_element_distribution_by_attribute(
    model: ifcopenshell.file,
    ifc_type: str,
    group_by_attribute: str = 'Name',
    include_percentages: bool = True,
    sort_by: str = 'count',
    sort_order: str = 'desc',
    empty_label: str = '(Empty)',
    include_elements: bool = False,
    element_attributes: Optional[List[str]] = None,
    value_parser: Optional[Callable[[str], str]] = None,
    filter_pset_name: Optional[str] = None,
    filter_prop_name: Optional[str] = None,
    filter_prop_value: Any = None,
    aggregate_pset_name: Optional[str] = None,
    aggregate_prop_name: Optional[str] = None,
    aggregate_aspects: List[Literal['sum', 'avg', 'min', 'max', 'count']] = ['count'],
    quantity_names: Optional[List[str]] = None,
    quantity_aggregation: str = 'sum',
    include_spatial_distribution: bool = False,
    storey_attribute: str = 'Name',
    filter_keywords: Optional[List[str]] = None,
    keyword_attributes: Optional[List[str]] = None,
    match_mode: Literal['any', 'all'] = 'any',
    # NAME PARSING PARAMETERS
    name_delimiter: Optional[str] = None,
    name_part_index: Optional[int] = 1,
    name_regex_pattern: Optional[str] = None,
    empty_label_after_parsing: Optional[str] = None,
    # SPATIAL FILTERING PARAMETERS
    storey_name: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Groups elements of a specified IFC type by a given attribute and returns counts, percentages,
    property aggregates, quantity aggregates, and optionally spatial distribution by building storey.
    Supports filtering by property sets, by keywords in element attributes, and by spatial containment (storey).

    Args:
        model: The loaded IFC model instance.
        ifc_type: The IFC class name(s) to analyze (e.g., 'IfcBeam', 'IfcFlowSegment').
        group_by_attribute: The attribute to group elements by (default: 'Name').
        include_percentages: Whether to calculate percentages (default: True).
        sort_by: Sort results by 'count' or 'attribute value' (default: 'count').
        sort_order: 'desc' or 'asc' (default: 'desc').
        empty_label: Label for None/empty values (default: '(Empty)').
        include_elements: If True, includes an 'elements' list in the result for each group.
        element_attributes: Optional list of specific attributes to extract for each element.
        value_parser: Optional callable to transform attribute values before grouping.
        filter_pset_name: The name of the PropertySet to check for filtering.
        filter_prop_name: The name of the Property within the set to evaluate.
        filter_prop_value: The value to match against for filtering.
        aggregate_pset_name: Name of property set containing values to aggregate.
        aggregate_prop_name: Name of property within the pset to aggregate.
        aggregate_aspects: List of statistics to calculate: 'sum', 'avg', 'min', 'max', 'count'.
                          Default is ['count'].
        quantity_names: Optional list of quantity names (e.g., 'GrossSideArea', 'NetVolume') to
                        extract from IfcElementQuantity sets and aggregate for each group.
        quantity_aggregation: The method to aggregate the quantities. Options: 'sum', 'mean', 'min', 'max'.
                             Default is 'sum'.
        include_spatial_distribution: When True, includes spatial distribution by storey for each group.
                                     Default is False.
        storey_attribute: Which attribute of IfcBuildingStorey to use as key (e.g., 'Name', 'GlobalId').
                         Default is 'Name'.
        filter_keywords: Optional list of strings to search for in element attributes.
        keyword_attributes: Optional list of attribute names to check for keywords (e.g., ['Name', 'ObjectType']).
                           Defaults to ['Name'] if filter_keywords is provided but keyword_attributes is None.
        match_mode: Strategy for matching keywords. 'any' means the element is kept if any keyword is found
                    in any of the attributes. 'all' means the element must contain all keywords (across attributes).
                    Defaults to 'any'.
        name_delimiter: Optional delimiter string to split the attribute value by before grouping.
                        Example: ':' splits 'Family:Type' into ['Family', 'Type'].
        name_part_index: Optional index of the split part to use. 0-based. Can be negative. Default is 1.
                         Used only if name_delimiter is provided and name_regex_pattern is None.
        name_regex_pattern: Optional regex pattern to extract a group from the attribute value.
                            Takes precedence over name_delimiter. Should contain a capturing group.
                            Example: r'Wide Flange:([A-Z0-9]+):' to extract 'W460X60'.
        empty_label_after_parsing: Label to use when parsing (delimiter/regex) produces empty/None results.
                                   Defaults to the value of `empty_label` if not specified.
        storey_name: Optional name of the storey to filter elements by. If provided, only elements
                     contained within the specified storey are analyzed. Matches against the
                     attribute specified by `storey_attribute`.

    Returns:
        Dict mapping attribute values to dicts containing statistics.
        Example without spatial distribution:
            {
                "TypeA": {"count": 10, "percentage": 50.0}
            }
        Example with spatial distribution:
            {
                "TypeA": {
                    "count": 10,
                    "percentage": 50.0,
                    "spatial_distribution": {
                        "Storey 1": {"count": 7, "percentage": 70.0},
                        "Storey 2": {"count": 3, "percentage": 30.0}
                    }
                }
            }

    Example Usage:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Get spaces on Level 3 grouped by function with areas
        >>> dist = get_element_distribution_by_attribute(
        ...     model, 'IfcSpace', group_by_attribute='LongName',
        ...     storey_name='3.etg', quantity_names=['NetFootprintArea']
        ... )
        >>> # Get beam types by splitting name
        >>> dist = get_element_distribution_by_attribute(
        ...     model, 'IfcBeam', group_by_attribute='Name',
        ...     name_delimiter=':', name_part_index=1
        ... )
    """
    # Input validation
    if model is None:
        raise ValueError("Model cannot be None")

    if not ifc_type:
        raise ValueError("ifc_type must be specified")

    allowed_sort_by = ['count', 'attribute value']
    if sort_by not in allowed_sort_by:
        raise ValueError(f"sort_by must be one of {allowed_sort_by}")

    allowed_sort_order = ['desc', 'asc']
    if sort_order not in allowed_sort_order:
        raise ValueError(f"sort_order must be one of {allowed_sort_order}")
        
    allowed_match_mode = ['any', 'all']
    if match_mode not in allowed_match_mode:
        raise ValueError(f"match_mode must be one of {allowed_match_mode}")

    allowed_aggregate_aspects = ['sum', 'avg', 'min', 'max', 'count']
    for aspect in aggregate_aspects:
        if aspect not in allowed_aggregate_aspects:
            raise ValueError(f"aggregate_aspects contains invalid value '{aspect}'. Must be one of {allowed_aggregate_aspects}")

    allowed_qty_agg = ['sum', 'mean', 'min', 'max']
    if quantity_aggregation not in allowed_qty_agg:
        raise ValueError(f"quantity_aggregation must be one of {allowed_qty_agg}")

    # Helper function to get storey for an element
    def get_storey_for_element(element: ifcopenshell.entity_instance, storey_attr: str = 'Name') -> str:
        """Find the storey that contains this element using inverse relationships."""
        try:
            # Use model.get_inverse for broad compatibility
            for rel in model.get_inverse(element):
                if rel.is_a('IfcRelContainedInSpatialStructure'):
                    container = rel.RelatingStructure
                    if container.is_a('IfcBuildingStorey'):
                        return getattr(container, storey_attr, 'Unknown')
                    elif container.is_a('IfcSpace') or container.is_a('IfcZone'):
                        # Traverse up: if the space/zone is in a storey, return that
                        for rel2 in model.get_inverse(container):
                            if rel2.is_a('IfcRelContainedInSpatialStructure'):
                                container2 = rel2.RelatingStructure
                                if container2.is_a('IfcBuildingStorey'):
                                    return getattr(container2, storey_attr, 'Unknown')
                elif rel.is_a('IfcRelAggregates'):
                    # Some elements might be aggregated directly by a storey
                    relating_obj = rel.RelatingObject
                    if relating_obj.is_a('IfcBuildingStorey'):
                        return getattr(relating_obj, storey_attr, 'Unknown')
        except (AttributeError, RuntimeError):
            pass
        return 'Unknown'

    # Determine flags
    aggregation_active = (
        aggregate_pset_name is not None and
        aggregate_prop_name is not None
    )

    quantity_extraction_active = quantity_names is not None and len(quantity_names) > 0

    filter_active = (
        filter_pset_name is not None and
        filter_prop_name is not None and
        filter_prop_value is not None
    )

    # Keyword filtering setup
    keyword_filter_active = False
    if filter_keywords and len(filter_keywords) > 0:
        keyword_filter_active = True
        if not keyword_attributes or len(keyword_attributes) == 0:
            keyword_attributes = ['Name']

    # Spatial filtering setup
    spatial_filter_active = storey_name is not None

    # Parsing setup
    string_parser_active = name_regex_pattern is not None or name_delimiter is not None
    
    # Retrieve elements
    elements = model.by_type(ifc_type)
    if not elements:
        return {}

    distribution: Dict[str, Dict[str, Any]] = {}
    skipped_attr = 0
    parsing_errors = 0
    filter_skipped = 0
    keyword_filter_skipped = 0
    spatial_filter_skipped = 0
    filter_error = 0
    aggregate_error = 0
    quantity_missing_count = 0
    spatial_missing_count = 0

    filtered_elements = []

    # 1. Filter elements
    for element in elements:
        keep_element = True
        
        # 1a. Spatial Filter
        if spatial_filter_active:
            current_storey = get_storey_for_element(element, storey_attribute)
            if current_storey != storey_name:
                spatial_filter_skipped += 1
                keep_element = False

        # 1b. Keyword Filter
        if keyword_filter_active and keep_element:
            matches_keywords = False
            try:
                lowered_keywords = [k.lower() for k in filter_keywords]
                keyword_found_status = [False] * len(lowered_keywords)
                
                for attr_name in keyword_attributes:
                    try:
                        attr_val = getattr(element, attr_name)
                        if attr_val is None:
                            continue
                        attr_str = str(attr_val).lower()
                        
                        for idx, kw in enumerate(lowered_keywords):
                            if kw in attr_str:
                                keyword_found_status[idx] = True
                    except AttributeError:
                        continue
                
                if match_mode == 'any':
                    if any(keyword_found_status):
                        matches_keywords = True
                elif match_mode == 'all':
                    if all(keyword_found_status):
                        matches_keywords = True
            except Exception:
                matches_keywords = False

            if not matches_keywords:
                keyword_filter_skipped += 1
                keep_element = False

        # 1c. Property Set Filter
        if filter_active and keep_element:
            matches_filter = False
            try:
                prop_val = ifcopenshell.util.element.get_pset(
                    element,
                    filter_pset_name,
                    filter_prop_name
                )
                if prop_val == filter_prop_value:
                    matches_filter = True
            except (AttributeError, KeyError, RuntimeError):
                filter_error += 1
            except Exception:
                filter_error += 1

            if matches_filter:
                keep_element = True
            else:
                filter_skipped += 1
                keep_element = False

        if keep_element:
            filtered_elements.append(element)

    if not filtered_elements:
        return {}

    # 2. Group elements and perform aggregation
    for element in filtered_elements:
        # Determine Group Key
        try:
            raw_value = getattr(element, group_by_attribute)
            
            if raw_value is None or (isinstance(raw_value, str) and str(raw_value).strip() == ''):
                key = empty_label
            else:
                source_str = str(raw_value)
                key = source_str
                
                if string_parser_active:
                    try:
                        candidate_key = None
                        
                        if name_regex_pattern:
                            match = re.search(name_regex_pattern, source_str)
                            if match:
                                if match.lastindex and match.lastindex >= 1:
                                    candidate_key = match.group(1)
                                else:
                                    candidate_key = match.group(0)
                        elif name_delimiter:
                            parts = source_str.split(name_delimiter)
                            idx = name_part_index if name_part_index is not None else 0
                            if idx < 0:
                                idx = len(parts) + idx
                                
                            if 0 <= idx < len(parts):
                                candidate_key = parts[idx].strip()
                        
                        if candidate_key is not None and candidate_key.strip() != '':
                            key = candidate_key
                        else:
                            key = empty_label_after_parsing if empty_label_after_parsing is not None else empty_label
                            
                    except Exception:
                        parsing_errors += 1
                        key = empty_label_after_parsing if empty_label_after_parsing is not None else empty_label
                
                if value_parser is not None:
                    try:
                        parsed_value = value_parser(key)
                        if parsed_value is None or (isinstance(parsed_value, str) and parsed_value.strip() == ''):
                            key = empty_label
                        else:
                            key = str(parsed_value)
                    except Exception:
                        skipped_attr += 1
                        continue
                        
        except AttributeError:
            skipped_attr += 1
            continue
        except Exception:
            skipped_attr += 1
            continue

        if key not in distribution:
            distribution[key] = {'count': 0}
            if include_percentages:
                distribution[key]['percentage'] = 0.0
            if include_elements:
                distribution[key]['elements'] = []
            if aggregation_active:
                distribution[key]['sum'] = 0.0
                distribution[key]['min'] = float('inf')
                distribution[key]['max'] = float('-inf')
                distribution[key]['val_count'] = 0
            if quantity_extraction_active:
                distribution[key]['quantities'] = {
                    q_name: {'sum': 0.0, 'min': float('inf'), 'max': float('-inf'), 'count': 0}
                    for q_name in quantity_names
                }
            if include_spatial_distribution:
                distribution[key]['spatial_distribution'] = {}

        distribution[key]['count'] += 1

        if include_elements:
            if element_attributes:
                elem_data = {}
                for attr in element_attributes:
                    try:
                        elem_data[attr] = getattr(element, attr)
                    except AttributeError:
                        elem_data[attr] = None
                distribution[key]['elements'].append(elem_data)
            else:
                distribution[key]['elements'].append(element)

        if aggregation_active:
            try:
                val = ifcopenshell.util.element.get_pset(
                    element,
                    aggregate_pset_name,
                    aggregate_prop_name
                )
                if val is not None:
                    num_val = float(val)
                    distribution[key]['sum'] += num_val
                    distribution[key]['min'] = min(distribution[key]['min'], num_val)
                    distribution[key]['max'] = max(distribution[key]['max'], num_val)
                    distribution[key]['val_count'] += 1
            except (ValueError, TypeError):
                aggregate_error += 1
            except (AttributeError, KeyError, RuntimeError):
                aggregate_error += 1
            except Exception:
                aggregate_error += 1

        if quantity_extraction_active:
            try:
                qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
                
                if qtos:
                    for q_name in quantity_names:
                        found_value = None
                        for pset_data in qtos.values():
                            if q_name in pset_data:
                                found_value = pset_data[q_name]
                                break 
                        
                        if found_value is not None and isinstance(found_value, (int, float)):
                            num_val = float(found_value)
                            stats = distribution[key]['quantities'][q_name]
                            stats['sum'] += num_val
                            stats['min'] = min(stats['min'], num_val)
                            stats['max'] = max(stats['max'], num_val)
                            stats['count'] += 1
                        else:
                            quantity_missing_count += 1
            except Exception:
                quantity_missing_count += 1

        if include_spatial_distribution:
            storey_key = get_storey_for_element(element, storey_attribute)
            if storey_key == 'Unknown':
                spatial_missing_count += 1
            
            if storey_key not in distribution[key]['spatial_distribution']:
                distribution[key]['spatial_distribution'][storey_key] = {'count': 0}
            distribution[key]['spatial_distribution'][storey_key]['count'] += 1

    # 3. Calculate final statistics
    total_valid = len(filtered_elements) - skipped_attr
    if include_percentages and total_valid > 0:
        for key in distribution:
            count = distribution[key]['count']
            distribution[key]['percentage'] = round((count / total_valid) * 100, 2)

    if aggregation_active:
        for key in distribution:
            if 'avg' in aggregate_aspects:
                val_count = distribution[key].get('val_count', 0)
                if val_count > 0:
                    distribution[key]['avg'] = distribution[key]['sum'] / val_count
                else:
                    distribution[key]['avg'] = 0.0

            requested_stats = set(aggregate_aspects)
            if 'sum' not in requested_stats:
                distribution[key].pop('sum', None)
            if 'min' not in requested_stats:
                distribution[key].pop('min', None)
            if 'max' not in requested_stats:
                distribution[key].pop('max', None)
            if 'avg' not in requested_stats:
                distribution[key].pop('avg', None)

            distribution[key].pop('val_count', None)

            if distribution[key].get('min') == float('inf'):
                distribution[key].pop('min', None)
            if distribution[key].get('max') == float('-inf'):
                distribution[key].pop('max', None)

    if quantity_extraction_active:
        for key in distribution:
            final_quantities = {}
            for q_name, stats in distribution[key]['quantities'].items():
                if stats['count'] == 0:
                    final_quantities[q_name] = None
                elif quantity_aggregation == 'sum':
                    final_quantities[q_name] = round(stats['sum'], 4)
                elif quantity_aggregation == 'mean':
                    final_quantities[q_name] = round(stats['sum'] / stats['count'], 4)
                elif quantity_aggregation == 'min':
                    final_quantities[q_name] = round(stats['min'], 4)
                elif quantity_aggregation == 'max':
                    final_quantities[q_name] = round(stats['max'], 4)
            distribution[key]['quantities'] = final_quantities

    if include_spatial_distribution:
        for key in distribution:
            group_count = distribution[key]['count']
            for storey, data in distribution[key]['spatial_distribution'].items():
                storey_count = data['count']
                if group_count > 0:
                    data['percentage'] = round((storey_count / group_count) * 100, 2)
                else:
                    data['percentage'] = 0.0

    # 4. Sort results
    reverse_sort = (sort_order == 'desc')

    def get_sort_key(item: tuple):
        key, data = item
        if sort_by == 'count':
            return data['count']
        elif sort_by == 'attribute value':
            return key.lower() if isinstance(key, str) else key
        return 0

    sorted_distribution = dict(
        sorted(distribution.items(), key=get_sort_key, reverse=reverse_sort)
    )

    # Reporting
    if spatial_filter_active and spatial_filter_skipped > 0:
        print(f"Info: {spatial_filter_skipped} elements filtered out (not in storey '{storey_name}').")
    if parsing_errors > 0:
        print(f"Warning: Parsing logic failed for {parsing_errors} elements.")
    if keyword_filter_active and keyword_filter_skipped > 0:
        print(f"Info: {keyword_filter_skipped} elements filtered out by keyword criteria.")
    if filter_active and filter_skipped > 0:
        print(f"Info: {filter_skipped} elements filtered out (did not match property criteria).")
    if filter_error > 0:
        print(f"Warning: {filter_error} elements skipped due to property access errors during filtering.")
    if skipped_attr > 0:
        print(f"Warning: Skipped {skipped_attr} elements due to missing attribute '{group_by_attribute}' or parsing errors.")
    if aggregation_active and aggregate_error > 0:
        print(f"Warning: Failed to aggregate property for {aggregate_error} elements (missing property or non-numeric value).")
    if quantity_extraction_active and quantity_missing_count > 0:
        print(f"Warning: {quantity_missing_count} quantity values could not be found or were non-numeric.")
    if include_spatial_distribution and spatial_missing_count > 0:
        print(f"Warning: Could not determine storey for {spatial_missing_count} elements.")

    return sorted_distribution