import ifcopenshell
from typing import Dict, List, Any, Optional


def get_model_standards_inventory(
    model: ifcopenshell.file,
    include_property_sets: bool = True,
    include_quantity_sets: bool = True,
    include_classifications: bool = True,
    classification_sample_limit: int = 10
) -> Dict[str, Any]:
    """
    Discovers and inventories the modeling standards, property sets, quantity sets, and 
    classification systems defined in an IFC model.

    This function answers the common question "What standards are applied in this model?" 
    by scanning for buildingSMART property sets (Pset_*), quantity sets (Qto_* or custom), 
    and classification system references (Uniformat, OmniClass, Uniclass, etc.).

    Args:
        model: The loaded IFC model instance
        include_property_sets: Whether to inventory all property sets
        include_quantity_sets: Whether to inventory all quantity sets
        include_classifications: Whether to extract classification system metadata
        classification_sample_limit: Maximum classification references to return

    Returns:
        Dict[str, Any] with keys:
            - 'property_sets': Sorted list of unique property set names found
            - 'quantity_sets': Sorted list of unique quantity set names found
            - 'classifications': Dict containing:
                - 'systems': List of IfcClassification entities with Name, Source, Edition, Location
                - 'references_count': Total count of IfcClassificationReference found
                - 'references_sample': List of sample references (up to limit) with Name and ID

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> standards = get_model_standards_inventory(model)
        >>> print(standards['property_sets'])
        ['Pset_WallCommon', 'Pset_DoorCommon', ...]
        >>> print(standards['classifications']['systems'])
        [{'Name': 'Uniformat', 'Source': 'http://www.csiorg.net/uniformat', ...}]
    """
    result: Dict[str, Any] = {
        'property_sets': [],
        'quantity_sets': [],
        'classifications': {
            'systems': [],
            'references_count': 0,
            'references_sample': []
        }
    }

    # Validate input
    if model is None:
        return result

    skipped_rels = 0

    # Extract property sets and quantity sets
    if include_property_sets or include_quantity_sets:
        pset_names = set()
        qto_names = set()

        for rel in model.by_type('IfcRelDefinesByProperties'):
            try:
                if rel.RelatingPropertyDefinition is None:
                    skipped_rels += 1
                    continue

                prop_def = rel.RelatingPropertyDefinition
                if prop_def is None:
                    skipped_rels += 1
                    continue

                name = prop_def.Name
                if name is None:
                    name = "Unnamed"

                # Check if it's a quantity set
                if prop_def.is_a('IfcElementQuantity'):
                    if include_quantity_sets:
                        qto_names.add(name)
                # Check if it's a property set
                elif prop_def.is_a('IfcPropertySet'):
                    if include_property_sets:
                        pset_names.add(name)

            except (AttributeError, RuntimeError):
                skipped_rels += 1
                continue

        result['property_sets'] = sorted(list(pset_names))
        result['quantity_sets'] = sorted(list(qto_names))

    # Extract classification systems
    if include_classifications:
        # Get classification systems
        systems = []
        for classification in model.by_type('IfcClassification'):
            try:
                system_info = {
                    'Name': getattr(classification, 'Name', None),
                    'Source': getattr(classification, 'Source', None),
                    'Edition': getattr(classification, 'Edition', None),
                    'Location': getattr(classification, 'Location', None)
                }
                systems.append(system_info)
            except (AttributeError, RuntimeError):
                continue

        result['classifications']['systems'] = systems

        # Get classification references
        refs = model.by_type('IfcClassificationReference')
        result['classifications']['references_count'] = len(refs)

        # Sample references
        sample_refs = []
        for ref in refs[:classification_sample_limit]:
            try:
                ref_info = {
                    'Name': getattr(ref, 'Name', None),
                    'ID': getattr(ref, 'Identification', None)
                }
                sample_refs.append(ref_info)
            except (AttributeError, RuntimeError):
                continue

        result['classifications']['references_sample'] = sample_refs

    return result