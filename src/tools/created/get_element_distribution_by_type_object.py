import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Callable, Union, Literal


def get_element_distribution_by_type_object(
    model: ifcopenshell.file,
    element_type: str,
    group_by_type_attribute: str = 'Name',
    include_element_details: bool = False,
    element_attributes: List[str] = ['Name', 'GlobalId'],
    include_percentages: bool = True,
    sort_by: Optional[str] = 'count',
    sort_order: str = 'desc',
    empty_label: str = 'No Type',
    filter_func: Optional[Callable[[Any], bool]] = None,
    pset_name: Optional[str] = None,
    property_name: Optional[str] = None,
    property_value: Any = None,
    quantities_to_aggregate: Optional[List[str]] = None,
    fallback_attributes: Optional[List[str]] = None,
    fallback_pset_name_keywords: Optional[List[str]] = None,
    include_materials: bool = False,
    material_detail_level: Literal['names', 'full'] = 'names',
    include_material_layers: bool = False,
    resolve_material_set: bool = True,
    group_by_attribute: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Groups elements of a specified IFC type by their associated TypeObject or by instance attributes,
    with optional filtering by element properties or custom function, and optional aggregation of
    element quantities.

    This function can operate in two modes:
    1. TypeObject grouping (default): Resolves the relationship between typed elements and their
       TypeObject definitions to enable analysis based on formal type classifications.
    2. Instance attribute grouping (when group_by_attribute is provided): Groups elements directly
       by a specified instance attribute (e.g., 'Name', 'Description', 'GlobalId'), bypassing
       TypeObject resolution entirely.

    Args:
        model: The loaded IFC model instance
        element_type: The IFC element class to query (e.g., 'IfcFurnishingElement', 'IfcDoor', 'IfcWindow')
        group_by_type_attribute: Attribute of the TypeObject to group by (default: 'Name').
            Only used when group_by_attribute is None. Can be 'Name', 'GlobalId', 'ObjectType',
            or other TypeObject attributes.
        group_by_attribute: Optional instance attribute to group by (e.g., 'Name', 'Description', 'GlobalId').
            When provided, bypasses TypeObject resolution and groups elements directly by this
            instance attribute. Takes precedence over group_by_type_attribute if both are provided.
            Useful when models lack well-defined TypeObjects or instance names contain type information.
        include_element_details: If True, includes lists of elements for each type group (default: False)
        element_attributes: Which element attributes to include when include_element_details=True
            (default: ['Name', 'GlobalId'])
        include_percentages: Whether to calculate percentage of total for each group (default: True)
        sort_by: Sort results by 'count', 'name', or None for unsorted (default: 'count')
        sort_order: 'asc' or 'desc' (default: 'desc')
        empty_label: Label for elements with no associated TypeObject or empty attribute value (default: 'No Type')
        filter_func: Optional callable that takes an element and returns True to include it.
            If provided, only elements passing this filter are counted.
        pset_name: Optional Property Set name to filter by (e.g., 'ArchiCADProperties').
            If provided along with property_name and property_value, filters elements
            where this property equals property_value.
        property_name: Optional Property name within the pset_name to filter by (e.g., 'Ebene').
        property_value: Value to match for the property. Comparison is strict equality.
        quantities_to_aggregate: Optional list of quantity names to aggregate for each type group
            (e.g., ['Length', 'Volume', 'Area']). If provided, traverses quantity sets and
            sums values for elements in each group. Result keys are prefixed with 'Total_'
            (e.g., 'Total_Length', 'Total_Volume').
        fallback_attributes: Optional list of element attributes (e.g., ['PredefinedType', 'ObjectType'])
            to check in order if the element has no TypeObject. Only used when group_by_attribute is None.
            The first non-empty value found will be used as the type classification.
        fallback_pset_name_keywords: Optional list of keywords (e.g., ['AC_Pset_', 'Geländer'])
            to search for within the element's Property Set names if the TypeObject and attributes
            are missing. Only used when group_by_attribute is None.
            The name of the matching Pset will be used as the type classification.
        include_materials: When True, extracts material information for each type by traversing
            HasAssociations → IfcRelAssociatesMaterial relationships (default: False).
        material_detail_level: Controls the depth of material information returned.
            'names' returns only material names. 'full' includes material names and layer details
            when include_material_layers is True (default: 'names').
        include_material_layers: When True, includes layer structure (thickness, material name,
            ventilation status) from a sample element for each type (default: False).
        resolve_material_set: Whether to resolve materials through IfcMaterialLayerSetUsage or
            directly from IfcMaterial (default: True).

    Returns:
        A dictionary where keys are the values from the grouping method (TypeObject attribute or
        instance attribute), and each value contains:
            - 'count': Number of elements in this group
            - 'percentage': Percentage of total (only if include_percentages=True)
            - 'type_id': GlobalId of the TypeObject, 'Instance:AttributeName', 'Attribute:xxx', or 'Pset:xxx'
            - 'elements': List of element details (only if include_element_details=True)
            - 'Total_{QuantityName}': Sum of each specified quantity (only if quantities_to_aggregate provided)
            - 'materials': List of unique material names used by this type (only if include_materials=True)
            - 'material_count': Number of unique materials (only if include_materials=True)
            - 'material_layers': List of layer details from sample element (only if include_materials=True and include_material_layers=True)

        Returns empty dict {} if no elements of the specified type are found or if all are filtered out.

    Example:
        >>> # Standard usage - group by TypeObject
        >>> result = get_element_distribution_by_type_object(model, 'IfcWall')

        >>> # Group by instance attribute (bypass TypeObject)
        >>> result = get_element_distribution_by_type_object(
        ...     model, 'IfcWall', group_by_attribute='Name'
        ... )

        >>> # With filtering by property and grouping by TypeObject
        >>> result = get_element_distribution_by_type_object(
        ...     model, 'IfcWall',
        ...     pset_name='Pset_WallCommon',
        ...     property_name='IsExternal',
        ...     property_value=True
        ... )

        >>> # With material analysis
        >>> result = get_element_distribution_by_type_object(
        ...     model, 'IfcWall', include_materials=True,
        ...     include_material_layers=True, material_detail_level='full'
        ... )

        >>> # Fallback usage: Group by PredefinedType if no TypeObject
        >>> result = get_element_distribution_by_type_object(
        ...     model, 'IfcRailing',
        ...     fallback_attributes=['PredefinedType']
        ... )
    """
    # Get all elements of the specified type
    elements = model.by_type(element_type)

    # Handle empty input
    if not elements:
        return {}

    # Validate sort_order
    if sort_order not in ('asc', 'desc'):
        sort_order = 'desc'

    # Validate material_detail_level
    if material_detail_level not in ('names', 'full'):
        material_detail_level = 'names'

    # Determine grouping mode
    use_instance_grouping = group_by_attribute is not None

    # Dictionary to store grouped results
    groups: Dict[str, Dict[str, Any]] = {}

    skipped_count = 0
    filtered_count = 0
    quantity_errors = 0
    total_count = 0
    material_errors = 0

    # Track first element for each type for material layer extraction
    sample_elements: Dict[str, Any] = {}

    for elem in elements:
        try:
            # --- Filtering Logic ---
            include_element = True

            # 1. Property-based filtering
            if pset_name and property_name:
                prop_match_found = False
                try:
                    # Iterate through IsDefinedBy relationships to find the property
                    for definition in elem.IsDefinedBy:
                        if hasattr(definition, 'RelatingPropertyDefinition'):
                            prop_def = definition.RelatingPropertyDefinition

                            # Check PSet name
                            if hasattr(prop_def, 'Name') and prop_def.Name == pset_name:
                                if hasattr(prop_def, 'HasProperties'):
                                    for prop in prop_def.HasProperties:
                                        # Check Property name
                                        if prop.Name == property_name:
                                            # Get value, handling IfcValue wrapper (NominalValue)
                                            nominal = getattr(prop, 'NominalValue', None)
                                            actual_value = None
                                            if nominal:
                                                actual_value = getattr(nominal, 'wrappedValue', nominal)

                                            # Compare values
                                            if actual_value == property_value:
                                                prop_match_found = True
                                            break
                        if prop_match_found:
                            break
                except AttributeError:
                    prop_match_found = False

                if not prop_match_found:
                    include_element = False
                    filtered_count += 1

            # 2. Custom function filtering
            if include_element and filter_func:
                try:
                    if not filter_func(elem):
                        include_element = False
                        filtered_count += 1
                except Exception:
                    # If filter function fails, exclude element to be safe
                    include_element = False
                    filtered_count += 1

            if not include_element:
                continue

            # --- Grouping Logic ---
            group_key = None
            type_id = 'Unknown'
            
            if use_instance_grouping:
                # Group by instance attribute, bypass TypeObject resolution
                group_key = getattr(elem, group_by_attribute, None)
                type_id = f"Instance:{group_by_attribute}"
                
                if group_key is None or group_key == '':
                    group_key = empty_label
                    type_id = 'Unknown'
                else:
                    group_key = str(group_key)
            else:
                # Group by TypeObject attribute
                type_obj = ifcopenshell.util.element.get_type(elem)

                if type_obj is not None:
                    # Get the grouping key from the TypeObject attribute
                    group_key = getattr(type_obj, group_by_type_attribute, None)
                    type_id = getattr(type_obj, 'GlobalId', 'Unknown')

                    if group_key is None:
                        group_key = empty_label
                        type_id = 'Unknown'
                else:
                    # No type object associated, try fallbacks
                    group_key = empty_label
                    type_id = 'Unknown'
                    found_fallback = False

                    # 1. Fallback to Attributes
                    if fallback_attributes:
                        for attr in fallback_attributes:
                            val = getattr(elem, attr, None)
                            if val is not None and val != '':
                                group_key = str(val)
                                type_id = f"Attribute:{attr}"
                                found_fallback = True
                                break
                    
                    # 2. Fallback to Pset Name Keywords
                    if not found_fallback and fallback_pset_name_keywords:
                        try:
                            psets = ifcopenshell.util.element.get_psets(elem, psets_only=True)
                            for pset_name_iter in psets.keys():
                                for keyword in fallback_pset_name_keywords:
                                    if keyword in pset_name_iter:
                                        group_key = pset_name_iter
                                        type_id = f"Pset:{pset_name_iter}"
                                        found_fallback = True
                                        break
                                if found_fallback:
                                    break
                        except RuntimeError:
                            # Error getting psets, skip fallback
                            pass

            # Initialize group if not exists
            if group_key not in groups:
                groups[group_key] = {
                    'count': 0,
                    'type_id': type_id,
                    'elements': []
                }
                # Initialize material tracking
                if include_materials:
                    groups[group_key]['materials'] = set()
                # Initialize quantity trackers for this group if aggregation requested
                if quantities_to_aggregate:
                    for qty_name in quantities_to_aggregate:
                        key = f'Total_{qty_name}'
                        groups[group_key][key] = 0.0

            # Track first element of this type for material layer extraction
            if include_materials and include_material_layers and group_key not in sample_elements:
                sample_elements[group_key] = elem

            # Increment count
            groups[group_key]['count'] += 1
            total_count += 1

            # --- Material Extraction ---
            if include_materials:
                try:
                    if hasattr(elem, 'HasAssociations'):
                        for assoc in elem.HasAssociations:
                            if assoc.is_a() == 'IfcRelAssociatesMaterial':
                                mat_rel = assoc.RelatingMaterial
                                
                                # Handle IfcMaterialLayerSetUsage
                                if mat_rel.is_a() == 'IfcMaterialLayerSetUsage' and resolve_material_set:
                                    layer_set = mat_rel.ForLayerSet
                                    for layer in layer_set.MaterialLayers:
                                        mat = layer.Material
                                        if hasattr(mat, 'Name'):
                                            groups[group_key]['materials'].add(mat.Name)
                                
                                # Handle direct IfcMaterial
                                elif mat_rel.is_a() == 'IfcMaterial':
                                    if hasattr(mat_rel, 'Name'):
                                        groups[group_key]['materials'].add(mat_rel.Name)
                except AttributeError:
                    material_errors += 1

            # --- Quantity Aggregation ---
            if quantities_to_aggregate:
                try:
                    qtos = ifcopenshell.util.element.get_psets(elem, qtos_only=True)
                    
                    for qset in qtos.values():
                        for qty_name in quantities_to_aggregate:
                            if qty_name in qset:
                                value = qset[qty_name]
                                if value is not None:
                                    try:
                                        numeric_value = float(value)
                                        key = f'Total_{qty_name}'
                                        groups[group_key][key] += numeric_value
                                    except (TypeError, ValueError):
                                        pass
                except Exception:
                    quantity_errors += 1

            # Add element details if requested
            if include_element_details:
                element_details = {}
                for attr in element_attributes:
                    element_details[attr] = getattr(elem, attr, '')
                groups[group_key]['elements'].append(element_details)

        except AttributeError:
            skipped_count += 1
            continue
        except RuntimeError:
            skipped_count += 1
            continue

    # Calculate percentages if requested
    if include_percentages and total_count > 0:
        for group_data in groups.values():
            group_data['percentage'] = round(
                (group_data['count'] / total_count) * 100, 1
            )

    # Remove 'elements' key if not requested
    if not include_element_details:
        for group_data in groups.values():
            if 'elements' in group_data:
                del group_data['elements']

    # Process material data - convert sets to lists and extract layer details
    if include_materials:
        for group_key, group_data in groups.items():
            # Convert set to sorted list
            group_data['materials'] = sorted(list(group_data['materials']))
            group_data['material_count'] = len(group_data['materials'])
            
            # Extract layer details from sample element if requested
            if include_material_layers and group_key in sample_elements:
                sample_elem = sample_elements[group_key]
                layers = []
                try:
                    if hasattr(sample_elem, 'HasAssociations'):
                        for assoc in sample_elem.HasAssociations:
                            if assoc.is_a() == 'IfcRelAssociatesMaterial':
                                mat_rel = assoc.RelatingMaterial
                                
                                if mat_rel.is_a() == 'IfcMaterialLayerSetUsage' and resolve_material_set:
                                    layer_set = mat_rel.ForLayerSet
                                    for layer in layer_set.MaterialLayers:
                                        layer_info = {}
                                        if material_detail_level == 'full':
                                            layer_info['Material'] = getattr(layer.Material, 'Name', 'Unknown')
                                            layer_info['Thickness'] = getattr(layer, 'LayerThickness', None)
                                            layer_info['IsVentilated'] = getattr(layer, 'IsVentilated', None)
                                            layers.append(layer_info)
                                        else:
                                            layer_info['Material'] = getattr(layer.Material, 'Name', 'Unknown')
                                            layers.append(layer_info)
                                elif mat_rel.is_a() == 'IfcMaterial':
                                    layer_info = {}
                                    layer_info['Material'] = getattr(mat_rel, 'Name', 'Unknown')
                                    layers.append(layer_info)
                except AttributeError:
                    pass
                
                if layers:
                    group_data['material_layers'] = layers

    # Sort results if requested
    if sort_by == 'count':
        reverse = sort_order == 'desc'
        groups = dict(
            sorted(groups.items(), key=lambda x: x[1]['count'], reverse=reverse)
        )
    elif sort_by == 'name':
        reverse = sort_order == 'desc'
        groups = dict(
            sorted(groups.items(), key=lambda x: str(x[0]), reverse=reverse)
        )

    # Report status
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} elements due to errors")
    if quantity_errors > 0:
        print(f"Warning: Quantity extraction errors for {quantity_errors} elements")
    if material_errors > 0:
        print(f"Warning: Material extraction errors for {material_errors} elements")

    return groups