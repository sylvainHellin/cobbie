import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def calculate_total_quantity_by_criteria(
    ifc_file,
    element_type: str,
    filter_criteria: Dict[str, Any],
    quantity_name: str,
    quantity_set: str = 'BaseQuantities'
) -> Dict[str, Any]:
    """
    Calculates the total sum of a specific quantity for IFC elements filtered by semantic criteria.
    
    This function combines element filtering, quantity extraction, and summation into one operation,
    answering questions like 'what is the total length of interior walls?' or 'what is the total area of exterior walls?'.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcWall', 'IfcSlab')
        filter_criteria: Dict with filtering options:
            - name_patterns: List of string patterns to match in element names
            - property_filters: List of dicts with 'property_set', 'property_name', 'property_value'
        quantity_name: Name of the quantity to extract (e.g., 'Length', 'Area', 'Volume')
        quantity_set: Name of the quantity set containing the quantity (default: 'BaseQuantities')
    
    Returns:
        Dict with:
            - total_quantity: float (sum of all matching quantities)
            - element_count: int (number of elements found)
            - elements: List of dicts with element details and individual quantities
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = calculate_total_quantity_by_criteria(
        ...     model,
        ...     'IfcWall',
        ...     {'name_patterns': ['Wand-Int']},
        ...     'Length'
        ... )
        >>> print(f"Total length: {result['total_quantity']} m")
    """
    try:
        # Initialize result structure
        result = {
            'total_quantity': 0.0,
            'element_count': 0,
            'elements': []
        }
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Extract filter criteria
        name_patterns = filter_criteria.get('name_patterns', [])
        property_filters = filter_criteria.get('property_filters', [])
        
        for element in elements:
            # Check if element matches filter criteria
            matches_criteria = False
            
            # Check name patterns
            if name_patterns:
                element_name = element.Name or ''
                if any(pattern in element_name for pattern in name_patterns):
                    matches_criteria = True
            else:
                matches_criteria = True  # No name filter, proceed to property checks
            
            # Check property filters
            if matches_criteria and property_filters:
                matches_criteria = False  # Reset, need to match at least one property filter
                
                for prop_filter in property_filters:
                    prop_set_name = prop_filter.get('property_set')
                    prop_name = prop_filter.get('property_name')
                    prop_value = prop_filter.get('property_value')
                    
                    if not all([prop_set_name, prop_name, prop_value is not None]):
                        continue
                    
                    # Check property sets
                    for rel in element.IsDefinedBy:
                        if rel.is_a('IfcRelDefinesByProperties'):
                            pset = rel.RelatingPropertyDefinition
                            if pset.is_a('IfcPropertySet') and pset.Name == prop_set_name:
                                for prop in pset.HasProperties:
                                    if (hasattr(prop, 'NominalValue') and 
                                        prop.Name == prop_name and 
                                        prop.NominalValue.wrappedValue == prop_value):
                                        matches_criteria = True
                                        break
                                if matches_criteria:
                                    break
                        elif pset.is_a('IfcElementQuantity') and pset.Name == prop_set_name:
                            # Also check quantity sets for property filters
                            for quant in pset.Quantities:
                                if quant.Name == prop_name:
                                    if hasattr(quant, 'LengthValue') and quant.LengthValue == prop_value:
                                        matches_criteria = True
                                        break
                                    elif hasattr(quant, 'AreaValue') and quant.AreaValue == prop_value:
                                        matches_criteria = True
                                        break
                                    elif hasattr(quant, 'VolumeValue') and quant.VolumeValue == prop_value:
                                        matches_criteria = True
                                        break
                            if matches_criteria:
                                break
                    if matches_criteria:
                        break
            
            # If element matches criteria, extract quantity
            if matches_criteria:
                quantity_value = 0.0
                
                # Extract quantity from specified quantity set
                for rel in element.IsDefinedBy:
                    if rel.is_a('IfcRelDefinesByProperties'):
                        qset = rel.RelatingPropertyDefinition
                        if qset.is_a('IfcElementQuantity') and qset.Name == quantity_set:
                            for quant in qset.Quantities:
                                if quant.Name == quantity_name:
                                    if hasattr(quant, 'LengthValue'):
                                        quantity_value = float(quant.LengthValue)
                                    elif hasattr(quant, 'AreaValue'):
                                        quantity_value = float(quant.AreaValue)
                                    elif hasattr(quant, 'VolumeValue'):
                                        quantity_value = float(quant.VolumeValue)
                                    break
                            break
                
                # Add element details to result
                element_info = {
                    'GlobalId': element.GlobalId,
                    'Name': element.Name,
                    'quantity': quantity_value
                }
                
                # Add basic element info
                if hasattr(element, 'ObjectType'):
                    element_info['ObjectType'] = element.ObjectType
                if hasattr(element, 'PredefinedType'):
                    element_info['PredefinedType'] = element.PredefinedType
                
                result['elements'].append(element_info)
                result['total_quantity'] += quantity_value
                result['element_count'] += 1
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'total_quantity': 0.0,
            'element_count': 0,
            'elements': [],
            'error': str(e)
        }