import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union


def get_spatial_breakdown_by_level(
    model: ifcopenshell.file,
    ifc_type: str,
    attributes: Optional[List[str]] = None,
    quantities: Optional[List[str]] = None,
    properties: Optional[Dict[str, str]] = None,
    include_totals: bool = True,
    sort_by: Optional[str] = 'Name',
    storey_attribute: str = 'Name'
) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves a breakdown of elements by building storey, including specified attributes, properties, or quantities for each element.
    
    This function traverses the spatial structure of the IFC model, grouping elements by their containing storey.
    It is designed for generating reports such as 'room areas by level' or 'door counts by floor'.
    
    Args:
        model: The loaded IFC model.
        ifc_type: The IFC class to retrieve (e.g., 'IfcSpace', 'IfcWindow', 'IfcDoor').
        attributes: List of element attributes to include (e.g., ['Name', 'LongName', 'GlobalId']).
                   Defaults to ['Name', 'GlobalId'].
        quantities: List of quantity names to extract (e.g., ['NetFloorArea', 'GrossFloorArea', 'Volume']).
                    Defaults to None.
        properties: Dictionary mapping property set names to property names to extract
                   (e.g., {'PSet_SpaceCommon': 'OccupancyNumber'}). Defaults to None.
        include_totals: Whether to calculate totals for numeric quantities. Defaults to True.
        sort_by: Attribute to sort elements by within each storey. Defaults to 'Name'.
        storey_attribute: Attribute to use for the storey key. Defaults to 'Name'.
    
    Returns:
        A dictionary keyed by storey name. Each value contains:
        - 'storey_info': Dict with storey details (Name, Elevation, GlobalId, id).
        - 'elements': List of dictionaries, one per element, containing requested attributes and values.
        - 'totals': Dict of summed values for requested quantities (if include_totals is True).
        - 'stats': Dict with processing statistics (total_elements, skipped_elements).
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> breakdown = get_spatial_breakdown_by_level(
        ...     model,
        ...     ifc_type='IfcSpace',
        ...     attributes=['Name', 'LongName'],
        ...     quantities=['NetFloorArea']
        ... )
        >>> for storey_name, data in breakdown.items():
        ...     print(f"{storey_name}: {len(data['elements'])} spaces")
    """
    # Set defaults
    if attributes is None:
        attributes = ['Name', 'GlobalId']
    if quantities is None:
        quantities = []
    if properties is None:
        properties = {}
    
    # Initialize result dictionary
    result: Dict[str, Dict[str, Any]] = {}
    
    # Get all storeys
    storeys = model.by_type('IfcBuildingStorey')
    
    if not storeys:
        return {}
    
    total_processed = 0
    total_skipped = 0
    
    for storey in storeys:
        # Get storey key
        storey_key = getattr(storey, storey_attribute, None)
        if storey_key is None:
            storey_key = f"Storey_{storey.id}"
        
        # Get storey info
        storey_info: Dict[str, Any] = {
            'Name': getattr(storey, 'Name', None),
            'Elevation': getattr(storey, 'Elevation', None),
            'GlobalId': getattr(storey, 'GlobalId', None),
            'id': storey.id
        }
        
        # Get all elements contained in this storey
        try:
            contained_elements = ifcopenshell.util.element.get_decomposition(storey)
        except (AttributeError, RuntimeError) as e:
            # If decomposition fails, create entry with empty elements
            result[storey_key] = {
                'storey_info': storey_info,
                'elements': [],
                'totals': {},
                'stats': {'total_elements': 0, 'skipped_elements': 0, 'error': str(e)}
            }
            continue
        
        # Filter for requested ifc_type
        elements = [e for e in contained_elements if e.is_a(ifc_type)]
        
        element_list: List[Dict[str, Any]] = []
        totals: Dict[str, float] = {q: 0.0 for q in quantities}
        skipped = 0
        
        for element in elements:
            try:
                element_data: Dict[str, Any] = {}
                
                # Extract attributes
                for attr in attributes:
                    element_data[attr] = getattr(element, attr, None)
                
                # Extract quantities from IsDefinedBy relationships
                if quantities and hasattr(element, 'IsDefinedBy'):
                    for definition in element.IsDefinedBy:
                        try:
                            if hasattr(definition, 'RelatingPropertyDefinition'):
                                prop_def = definition.RelatingPropertyDefinition
                                if prop_def and prop_def.is_a('IfcElementQuantity'):
                                    for quant in prop_def.Quantities:
                                        quant_name = quant.Name
                                        if quant_name in quantities:
                                            # Handle different quantity types
                                            if hasattr(quant, 'AreaValue'):
                                                element_data[quant_name] = quant.AreaValue
                                            elif hasattr(quant, 'LengthValue'):
                                                element_data[quant_name] = quant.LengthValue
                                            elif hasattr(quant, 'VolumeValue'):
                                                element_data[quant_name] = quant.VolumeValue
                                            elif hasattr(quant, 'CountValue'):
                                                element_data[quant_name] = quant.CountValue
                                            elif hasattr(quant, 'WeightValue'):
                                                element_data[quant_name] = quant.WeightValue
                        except AttributeError:
                            continue
                
                # Extract properties from IsDefinedBy relationships
                if properties and hasattr(element, 'IsDefinedBy'):
                    for definition in element.IsDefinedBy:
                        try:
                            if hasattr(definition, 'RelatingPropertyDefinition'):
                                prop_def = definition.RelatingPropertyDefinition
                                if prop_def and prop_def.is_a('IfcPropertySet'):
                                    pset_name = prop_def.Name
                                    if pset_name in properties:
                                        prop_name = properties[pset_name]
                                        for prop in prop_def.HasProperties:
                                            if prop.Name == prop_name:
                                                if hasattr(prop, 'NominalValue'):
                                                    element_data[f"{pset_name}.{prop_name}"] = prop.NominalValue.wrappedValue
                        except (AttributeError, KeyError):
                            continue
                
                element_list.append(element_data)
                
                # Update totals
                if include_totals:
                    for q in quantities:
                        val = element_data.get(q)
                        if isinstance(val, (int, float)):
                            totals[q] += val
                
                total_processed += 1
                
            except AttributeError as e:
                skipped += 1
                total_skipped += 1
                continue
        
        # Sort elements if requested
        if sort_by:
            try:
                element_list.sort(key=lambda x: str(x.get(sort_by, '')))
            except (AttributeError, TypeError):
                pass
        
        result[storey_key] = {
            'storey_info': storey_info,
            'elements': element_list,
            'totals': totals if include_totals else {},
            'stats': {'total_elements': len(elements), 'skipped_elements': skipped}
        }
    
    return result