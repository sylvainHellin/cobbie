import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_elements_with_quantities(
    ifc_file,
    element_type: str,
    filter_keywords: Optional[List[str]] = None,
    quantity_types: Optional[List[str]] = None,
    include_summary: bool = True
) -> Dict[str, Any]:
    """
    Comprehensively analyzes IFC elements of a specified type, extracting both property sets and quantities with safe error handling.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSpace', 'IfcSlab', 'IfcWall')
        filter_keywords: Optional list of keywords to filter elements by (searches Name, ObjectType, LongName)
        quantity_types: Optional list of quantity types to extract (default: ['AreaValue', 'LengthValue', 'VolumeValue'])
        include_summary: Whether to include summary statistics (default: True)
    
    Returns:
        Dict containing:
        - 'elements': List of element dictionaries with properties and quantities
        - 'summary': Summary statistics including totals, counts, and filtered results
        - 'total_area': Sum of all area quantities found
        - 'filtered_elements': Elements matching filter_keywords
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_elements_with_quantities(model, 'IfcSpace', ['parking', 'garage'])
        >>> print(f"Total area: {result['total_area']} m²")
    """
    if quantity_types is None:
        quantity_types = ['AreaValue', 'LengthValue', 'VolumeValue']
    
    # Get all elements of the specified type
    elements = ifc_file.by_type(element_type)
    
    elements_data = []
    filtered_elements = []
    total_area = 0.0
    all_quantities = {qty_type: [] for qty_type in quantity_types}
    
    for element in elements:
        element_info = {
            'id': element.id(),
            'GlobalId': getattr(element, 'GlobalId', None),
            'Name': getattr(element, 'Name', None),
            'ObjectType': getattr(element, 'ObjectType', None),
            'LongName': getattr(element, 'LongName', None),
            'Properties': {},
            'Quantities': {}
        }
        
        # Check if element matches filter keywords
        matches_filter = False
        if filter_keywords:
            searchable_text = ' '.join([
                str(element_info['Name'] or ''),
                str(element_info['ObjectType'] or ''),
                str(element_info['LongName'] or '')
            ]).lower()
            
            for keyword in filter_keywords:
                if keyword.lower() in searchable_text:
                    matches_filter = True
                    break
        
        # Extract property sets safely
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            if psets:
                element_info['Properties'] = psets
        except Exception as e:
            element_info['Properties'] = {'error': str(e)}
        
        # Extract quantities safely using the pattern from execution history
        try:
            # Look for IfcElementQuantity relationships
            for rel in element.IsDefinedBy:
                if rel.is_a('IfcRelDefinesByProperties'):
                    relating_prop = rel.RelatingPropertyDefinition
                    if relating_prop and relating_prop.is_a('IfcElementQuantity'):
                        quantity_name = relating_prop.Name or 'Unnamed'
                        element_info['Quantities'][quantity_name] = {}
                        
                        for qty in relating_prop.Quantities:
                            qty_name = qty.Name or 'Unnamed'
                            qty_value = None
                            
                            # Check for different quantity types
                            if hasattr(qty, 'AreaValue'):
                                qty_value = qty.AreaValue
                                all_quantities['AreaValue'].append(qty_value)
                                total_area += qty_value
                            elif hasattr(qty, 'LengthValue'):
                                qty_value = qty.LengthValue
                                all_quantities['LengthValue'].append(qty_value)
                            elif hasattr(qty, 'VolumeValue'):
                                qty_value = qty.VolumeValue
                                all_quantities['VolumeValue'].append(qty_value)
                            
                            element_info['Quantities'][quantity_name][qty_name] = qty_value
        except Exception as e:
            element_info['Quantities'] = {'error': str(e)}
        
        # Also try to get quantities using the utility function
        try:
            qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
            if qtos:
                # Merge with existing quantities
                for qset_name, qset_props in qtos.items():
                    if qset_name not in element_info['Quantities']:
                        element_info['Quantities'][qset_name] = {}
                    element_info['Quantities'][qset_name].update(qset_props)
                    
                    # Track area values for total
                    for prop_name, prop_value in qset_props.items():
                        if isinstance(prop_value, (int, float)) and 'area' in prop_name.lower():
                            all_quantities['AreaValue'].append(prop_value)
                            total_area += prop_value
        except Exception as e:
            pass  # Ignore errors from utility function, we already have manual extraction
        
        elements_data.append(element_info)
        if matches_filter:
            filtered_elements.append(element_info)
    
    # Prepare summary
    summary = {
        'total_elements': len(elements_data),
        'filtered_count': len(filtered_elements),
        'quantity_totals': {}
    }
    
    for qty_type, values in all_quantities.items():
        if values:
            summary['quantity_totals'][qty_type] = {
                'count': len(values),
                'total': sum(values),
                'average': sum(values) / len(values),
                'min': min(values),
                'max': max(values)
            }
    
    result = {
        'elements': elements_data,
        'summary': summary if include_summary else {},
        'total_area': total_area,
        'filtered_elements': filtered_elements
    }
    
    return result