import ifcopenshell
from typing import Any, Dict, List, Optional

def get_entity_metadata(
    entity: ifcopenshell.entity_instance,
    attributes: List[str],
    include_psets: bool = True,
    pset_whitelist: Optional[List[str]] = None,
    property_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Extracts attributes and property sets from an IFC entity instance into a structured dictionary.

    This helper function retrieves standard IFC attributes and associated property sets (Psets)
    defined by IfcRelDefinesByProperties relationships. It handles missing attributes gracefully
    and allows filtering of property sets by name, as well as filtering individual properties within
    those sets.

    Args:
        entity (ifcopenshell.entity_instance): The IFC entity to analyze (e.g., IfcProject, IfcSlab).
        attributes (List[str]): List of attribute names to extract (e.g., ['Name', 'GlobalId']).
            Returns None if an attribute is missing or effectively empty (None or "").
        include_psets (bool, optional): Flag to include property sets defined by IfcRelDefinesByProperties.
            Defaults to True.
        pset_whitelist (Optional[List[str]], optional): Optional list of specific Pset names to retrieve.
            If None, retrieves all available Psets. Defaults to None.
        property_names (Optional[List[str]], optional): Optional list of specific property names to extract
            from the resolved Psets. If None, retrieves all properties within the allowed Psets.
            Defaults to None. This filter is applied *after* the pset_whitelist.

    Returns:
        Dict[str, Any]: A dictionary with two keys:
            - 'attributes': A dictionary mapping requested attribute names to their values.
                Values are None if the attribute is missing or empty.
            - 'psets': A dictionary where keys are Pset names and values are dictionaries
                of property names and their wrapped values (e.g., IfcLabel objects).

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> slab = model.by_type('IfcSlab')[0]
        >>> # Get all attributes and all properties in 'PSet_Revit_Dimensions'
        >>> data = get_entity_metadata(slab, ['Name'], pset_whitelist=['PSet_Revit_Dimensions'])
        >>> # Get only 'Area' and 'Volume' from available Psets
        >>> specific_data = get_entity_metadata(slab, ['Name'], property_names=['Area', 'Volume'])
        >>> print(specific_data['psets'])
    """
    result: Dict[str, Any] = {
        'attributes': {},
        'psets': {}
    }

    # 1. Extract Attributes
    for attr_name in attributes:
        # Use getattr to safely access attributes
        attr_value = getattr(entity, attr_name, None)
        
        # Check for empty: None or empty string "". 
        # Note: We preserve 0.0 or empty lists as they may be valid data in IFC.
        if attr_value is None or attr_value == "":
            result['attributes'][attr_name] = None
        else:
            result['attributes'][attr_name] = attr_value

    # 2. Extract Property Sets (Psets)
    if include_psets:
        # Optimization: Convert property_names list to set for O(1) lookup
        property_filter = None
        if property_names is not None:
            property_filter = set(property_names)

        # IsDefinedBy is an inverse attribute. It returns a list of relationships.
        definitions = getattr(entity, "IsDefinedBy", [])
        
        # Ensure definitions is iterable (safety check for different IFC versions/implementations)
        if not isinstance(definitions, (list, tuple)):
            definitions = [definitions]

        for definition in definitions:
            try:
                # We only care about IfcRelDefinesByProperties
                if definition.is_a('IfcRelDefinesByProperties'):
                    pset = definition.RelatingPropertyDefinition
                    pset_name = pset.Name
                    
                    # Apply whitelist filter if provided
                    if pset_whitelist is not None and pset_name not in pset_whitelist:
                        continue
                    
                    # Extract properties
                    props: Dict[str, Any] = {}
                    if hasattr(pset, 'HasProperties'):
                        for prop in pset.HasProperties:
                            # Apply property_names filter if provided
                            if property_filter is None or prop.Name in property_filter:
                                # Store the NominalValue which is the wrapped object (e.g., IfcLabel)
                                props[prop.Name] = prop.NominalValue
                    
                    if props:
                        result['psets'][pset_name] = props
                        
            except (AttributeError, RuntimeError):
                # Skip this definition if it's malformed or not accessible
                continue

    return result