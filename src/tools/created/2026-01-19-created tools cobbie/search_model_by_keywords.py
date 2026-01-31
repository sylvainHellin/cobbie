import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional


def search_model_by_keywords(
    model: ifcopenshell.file,
    keywords: List[str],
    search_targets: List[str] = ['pset_names', 'element_names', 'element_types'],
    element_types_to_scan: Optional[List[str]] = None,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Performs a comprehensive keyword search across multiple semantic layers of an IFC model
    to identify where specific concepts might be defined.

    Args:
        model: The loaded IFC model.
        keywords: List of keywords to search for (e.g., ['thermal', 'bridge', 'conductivity']).
        search_targets: Scope of the search. Options: 'pset_names', 'element_names',
                       'element_types', 'material_names', 'material_properties', 'property_values'.
                       Defaults to ['pset_names', 'element_names', 'element_types'].
        element_types_to_scan: Specific IFC types to check for element name/value matches
                              (e.g., ['IfcWall', 'IfcSlab']). If None, scans all standard product elements.
        case_sensitive: Whether the match is case sensitive. Defaults to False.

    Returns:
        A dictionary categorizing findings. Example:
        {
            'pset_matches': [{'Name': 'PSet_Thermal', 'id': 123}],
            'element_name_matches': [{'Type': 'IfcWall', 'Name': 'Thermal Barrier Wall', 'GlobalId': '...'}],
            'element_type_matches': ['IfcThermalBridge'],
            'material_matches': [{'Name': 'Insulation', 'id': 456, 'Properties': [...]}],
            'property_value_matches': [
                {
                    'ElementGlobalId': '...',
                    'ElementName': 'Wall',
                    'ElementType': 'IfcWall',
                    'PSetName': 'PSet_Common',
                    'PropertyName': 'Description',
                    'Value': 'Thermal Barrier'
                }
            ],
            'search_stats': {...}
        }

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> results = search_model_by_keywords(
        ...     model,
        ...     keywords=['thermal', 'bridge'],
        ...     search_targets=['pset_names', 'element_names', 'property_values']
        ... )
        >>> print(results['property_value_matches'])
    """
    # --- Input Validation ---
    if not keywords:
        return {
            'pset_matches': [],
            'element_name_matches': [],
            'element_type_matches': [],
            'material_matches': [],
            'property_value_matches': [],
            'search_stats': {'error': 'No keywords provided'}
        }

    if not model:
        return {
            'pset_matches': [],
            'element_name_matches': [],
            'element_type_matches': [],
            'material_matches': [],
            'property_value_matches': [],
            'search_stats': {'error': 'Invalid model'}
        }

    # --- Keyword Preparation ---
    if not case_sensitive:
        keywords_lower = [kw.lower() for kw in keywords]
    else:
        keywords_lower = keywords

    def _matches(text: str) -> bool:
        """Check if text matches any of the keywords."""
        if text is None:
            return False
        check_text = text if case_sensitive else text.lower()
        return any(kw in check_text for kw in keywords_lower)

    # --- Result Initialization ---
    results = {
        'pset_matches': [],
        'element_name_matches': [],
        'element_type_matches': [],
        'material_matches': [],
        'property_value_matches': []
    }

    # --- Statistics Tracking ---
    stats = {
        'psets_processed': 0,
        'elements_processed': 0,
        'element_types_checked': 0,
        'materials_processed': 0,
        'properties_scanned_count': 0,
        'skipped_elements': 0
    }

    # --- Helper: Get Elements to Scan ---
    def _get_elements_to_scan():
        """Determines the list of elements to scan based on inputs."""
        if element_types_to_scan:
            elems = []
            for et in element_types_to_scan:
                try:
                    elems.extend(model.by_type(et))
                except RuntimeError:
                    pass
            return elems
        else:
            # Default scan types: Products, Spaces, and Project metadata holders
            default_types = [
                'IfcWall', 'IfcSlab', 'IfcBeam', 'IfcColumn', 'IfcDoor', 'IfcWindow',
                'IfcRoof', 'IfcCovering', 'IfcRailing', 'IfcStair', 'IfcBuildingElementProxy',
                'IfcMember', 'IfcPlate', 'IfcFooting', 'IfcDiscreteAccessory', 'IfcFastener',
                'IfcMechanicalFastener', 'IfcFurnishingElement', 'IfcSpace', 'IfcBuilding', 'IfcProject'
            ]
            elems = []
            for et in default_types:
                try:
                    elems.extend(model.by_type(et))
                except RuntimeError:
                    pass
            return elems

    # --- Search: Property Set Names ---
    if 'pset_names' in search_targets:
        try:
            all_psets = model.by_type('IfcPropertySet')
            stats['psets_processed'] = len(all_psets)

            for pset in all_psets:
                pset_name = getattr(pset, 'Name', None)
                if pset_name and _matches(pset_name):
                    results['pset_matches'].append({
                        'Name': pset_name,
                        'id': pset.id()
                    })
        except (AttributeError, RuntimeError) as e:
            stats['psets_error'] = str(e)

    # --- Search: Element Types ---
    if 'element_types' in search_targets:
        try:
            type_counts = {}
            for element in model:
                elem_type = element.is_a()
                if elem_type not in type_counts:
                    type_counts[elem_type] = 0
                type_counts[elem_type] += 1

            stats['element_types_checked'] = len(type_counts)

            for elem_type in type_counts.keys():
                if _matches(elem_type):
                    results['element_type_matches'].append(elem_type)
        except (AttributeError, RuntimeError) as e:
            stats['element_types_error'] = str(e)

    # --- Search: Element Names & Property Values ---
    # Both require iterating over elements, so we group them to avoid double iteration
    needs_element_scan = 'element_names' in search_targets or 'property_values' in search_targets
    elements_to_check = []

    if needs_element_scan:
        elements_to_check = _get_elements_to_scan()
        # Update stats for elements processed
        stats['elements_processed'] = len(elements_to_check)

        for elem in elements_to_check:
            try:
                elem_name = getattr(elem, 'Name', None)
                elem_type = elem.is_a()
                elem_id = getattr(elem, 'GlobalId', None)

                # Search Element Name
                if 'element_names' in search_targets:
                    if elem_name and _matches(elem_name):
                        results['element_name_matches'].append({
                            'Type': elem_type,
                            'Name': elem_name,
                            'GlobalId': elem_id
                        })

                # Search Property Values
                if 'property_values' in search_targets:
                    try:
                        psets = ifcopenshell.util.element.get_psets(elem)
                        if psets:
                            for pset_name, props in psets.items():
                                for prop_name, prop_value in props.items():
                                    stats['properties_scanned_count'] += 1
                                    # Only search string properties
                                    if isinstance(prop_value, str) and _matches(prop_value):
                                        results['property_value_matches'].append({
                                            'ElementGlobalId': elem_id,
                                            'ElementName': elem_name,
                                            'ElementType': elem_type,
                                            'PSetName': pset_name,
                                            'PropertyName': prop_name,
                                            'Value': prop_value
                                        })
                    except (RuntimeError, AttributeError):
                        stats['skipped_elements'] += 1
                        continue

            except AttributeError:
                stats['skipped_elements'] += 1
                continue

    # --- Search: Materials ---
    if 'material_names' in search_targets or 'material_properties' in search_targets:
        try:
            all_materials = model.by_type('IfcMaterial')
            stats['materials_processed'] = len(all_materials)

            material_dict = {}

            for material in all_materials:
                mat_name = getattr(material, 'Name', 'Unnamed')
                mat_id = material.id()

                # Check material name
                name_match = _matches(mat_name) if 'material_names' in search_targets else False

                # Check material properties
                matching_props = []
                if 'material_properties' in search_targets:
                    try:
                        psets = ifcopenshell.util.element.get_psets(material)
                        if psets:
                            for p_name, p_props in psets.items():
                                for prop_n, prop_v in p_props.items():
                                    if isinstance(prop_v, str) and _matches(prop_v):
                                        matching_props.append({
                                            'PSetName': p_name,
                                            'PropertyName': prop_n
                                        })
                    except Exception:
                        pass

                if name_match or matching_props:
                    if mat_name not in material_dict:
                        material_dict[mat_name] = {'Name': mat_name, 'id': mat_id, 'Properties': []}
                    if matching_props:
                        material_dict[mat_name]['Properties'].extend(matching_props)

            results['material_matches'] = list(material_dict.values())

        except (AttributeError, RuntimeError) as e:
            stats['materials_error'] = str(e)

    results['search_stats'] = stats
    return results
