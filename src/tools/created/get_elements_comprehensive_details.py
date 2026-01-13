import ifcopenshell
from typing import Dict, List, Any, Optional

def get_elements_comprehensive_details(
    model: ifcopenshell.file,
    ifc_type: Optional[str] = None,
    element_id: Optional[str] = None,
    include_attributes: List[str] = ['Name', 'GlobalId', 'ObjectType'],
    include_type_object: bool = True,
    include_properties: bool = True,
    include_quantities: bool = True
) -> Dict[str, Dict[str, Any]]:
    """
    Extracts complete attribute, property, and quantity data for elements of a specified IFC type.
    This function is designed for scenarios where specific property names or sets are unknown 
    (e.g., vendor-specific exports) or when a full profile is required.

    Args:
        model: The loaded IFC model.
        ifc_type: The IFC class name to query (e.g., 'IfcBeam'). Optional if element_id is provided.
        element_id: GlobalId of a specific element to query. If provided, ifc_type is ignored.
        include_attributes: List of direct attributes to include. Defaults to ['Name', 'GlobalId', 'ObjectType'].
        include_type_object: Whether to resolve the TypeObject name. Defaults to True.
        include_properties: Whether to extract all properties. Defaults to True.
        include_quantities: Whether to extract all quantities. Defaults to True.

    Returns:
        A dictionary where keys are element GlobalIds and values are nested dictionaries 
        containing 'Attributes', 'TypeObject', 'Quantities' (grouped by set), 
        and 'Properties' (grouped by set).
        
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> details = get_elements_comprehensive_details(model, 'IfcBeam')
        >>> for guid, data in details.items():
        ...     print(data['Attributes']['Name'])
    """
    results: Dict[str, Dict[str, Any]] = {}
    skipped = 0
    
    # Validate inputs
    if not model:
        return {}
    
    # Determine elements to process
    elements = []
    if element_id:
        try:
            elem = model.by_guid(element_id)
            if elem:
                elements = [elem]
        except RuntimeError:
            # GUID might be invalid or not found
            pass
    elif ifc_type:
        elements = model.by_type(ifc_type)
    else:
        print("Warning: Either ifc_type or element_id must be provided.")
        return {}

    if not elements:
        return {}

    for element in elements:
        try:
            # Safely get GlobalId
            element_guid = getattr(element, 'GlobalId', None)
            if not element_guid:
                skipped += 1
                continue
                
            element_data: Dict[str, Any] = {
                'Attributes': {},
                'TypeObject': None,
                'Properties': {},
                'Quantities': {}
            }
            
            # 1. Extract Attributes
            for attr in include_attributes:
                try:
                    element_data['Attributes'][attr] = getattr(element, attr)
                except AttributeError:
                    element_data['Attributes'][attr] = None
            
            # 2. Resolve TypeObject via IsTypedBy
            if include_type_object:
                # Use getattr to handle cases where IsTypedBy might not exist on the instance
                is_typed_by = getattr(element, 'IsTypedBy', [])
                if is_typed_by:
                    for rel in is_typed_by:
                        if hasattr(rel, 'RelatingType'):
                            type_obj = rel.RelatingType
                            element_data['TypeObject'] = getattr(type_obj, 'Name', None)
                            break

            # 3. Process IsDefinedBy (Properties and Quantities)
            if include_properties or include_quantities:
                # Use getattr to handle missing attribute
                is_defined_by = getattr(element, 'IsDefinedBy', [])
                for definition in is_defined_by:
                    try:
                        if not hasattr(definition, 'RelatingPropertyDefinition'):
                            continue
                            
                        rel_def = definition.RelatingPropertyDefinition
                        set_name = getattr(rel_def, 'Name', 'UnknownSet')
                        
                        # Handle Quantities (IfcElementQuantity)
                        if include_quantities and rel_def.is_a('IfcElementQuantity'):
                            if set_name not in element_data['Quantities']:
                                element_data['Quantities'][set_name] = {}
                            
                            quantities = getattr(rel_def, 'Quantities', [])
                            for qto in quantities:
                                val = None
                                if hasattr(qto, 'LengthValue'): val = qto.LengthValue
                                elif hasattr(qto, 'AreaValue'): val = qto.AreaValue
                                elif hasattr(qto, 'VolumeValue'): val = qto.VolumeValue
                                elif hasattr(qto, 'WeightValue'): val = qto.WeightValue
                                elif hasattr(qto, 'CountValue'): val = qto.CountValue
                                elif hasattr(qto, 'TimeValue'): val = qto.TimeValue
                                elif hasattr(qto, 'NumericValue'): val = qto.NumericValue
                                
                                element_data['Quantities'][set_name][qto.Name] = val

                        # Handle Properties (IfcPropertySet)
                        elif include_properties and rel_def.is_a('IfcPropertySet'):
                            if set_name not in element_data['Properties']:
                                element_data['Properties'][set_name] = {}
                                
                            has_properties = getattr(rel_def, 'HasProperties', [])
                            for prop in has_properties:
                                val = None
                                if prop.is_a('IfcPropertySingleValue'):
                                    if hasattr(prop.NominalValue, 'wrappedValue'):
                                        val = prop.NominalValue.wrappedValue
                                    else:
                                        val = prop.NominalValue
                                elif prop.is_a('IfcPropertyListValue'):
                                    val = []
                                    if hasattr(prop, 'ListValues'):
                                        for v in prop.ListValues:
                                            if hasattr(v, 'wrappedValue'):
                                                val.append(v.wrappedValue)
                                            else:
                                                val.append(v)
                                elif prop.is_a('IfcPropertyBoundedValue'):
                                    # Handling bounded values (upper/lower limit)
                                    if hasattr(prop, 'UpperBoundValue') and hasattr(prop.UpperBoundValue, 'wrappedValue'):
                                        val = f"Upper: {prop.UpperBoundValue.wrappedValue}"
                                    elif hasattr(prop, 'LowerBoundValue') and hasattr(prop.LowerBoundValue, 'wrappedValue'):
                                        val = f"Lower: {prop.LowerBoundValue.wrappedValue}"
                                    
                                element_data['Properties'][set_name][prop.Name] = val
                    except AttributeError as e:
                        # Skip this specific definition if structure is unexpected
                        continue

            results[element_guid] = element_data

        except Exception as e:
            # Broad catch for the element loop to ensure one bad element doesn't stop processing
            # However, we log specific error context
            elem_name = getattr(element, 'Name', 'Unknown')
            elem_id = getattr(element, 'GlobalId', 'Unknown')
            print(f"Warning: Skipped element '{elem_name}' ({elem_id}) due to error: {e}")
            skipped += 1
            continue

    if skipped > 0:
        print(f"Info: Skipped {skipped} elements due to errors or missing data.")
        
    return results