import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def extract_and_aggregate_quantities_by_keywords(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    include_keywords: List[str],
    exclude_keywords: Optional[List[str]] = None,
    search_fields: List[str] = ['Name', 'ObjectType'],
    quantity_property: str = 'Volume',
    property_sets: Optional[List[str]] = None,
    aggregation: str = 'sum',
    case_sensitive: bool = False,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Finds IFC elements by semantic keywords and extracts/aggregates quantitative properties.
    
    This function answers questions like 'what is the total volume of concrete in foundation?' 
    or 'what is the total area of exterior walls?' by combining element discovery with 
    quantitative analysis.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element types to search (e.g., ['IfcWall', 'IfcWallStandardCase'])
        include_keywords: List of keywords elements must contain (e.g., ['foundation', 'concrete'])
        exclude_keywords: Optional list of keywords elements must not contain
        search_fields: Fields to search for keywords (default: ['Name', 'ObjectType'])
        quantity_property: Name of quantitative property to extract (e.g., 'Volume', 'Area', 'Length')
        property_sets: List of property sets to search for the quantity (default: common quantity sets)
        aggregation: How to aggregate results ('sum', 'average', 'count', 'max', 'min', default: 'sum')
        case_sensitive: Whether keyword matching is case sensitive (default: False)
        include_details: Whether to return individual element details (default: False)
    
    Returns:
        Dict containing aggregated value, count of matching elements, and optional element details.
        Structure: {
            'aggregated_value': float,
            'count': int,
            'elements_with_quantities': int,
            'elements': List[Dict] (if include_details=True),
            'error': str (if error occurred)
        }
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = extract_and_aggregate_quantities_by_keywords(
        ...     ifc_file=model,
        ...     element_types=['IfcWall', 'IfcWallStandardCase'],
        ...     include_keywords=['foundation', 'concrete'],
        ...     quantity_property='Volume'
        ... )
        >>> print(f"Total volume: {result['aggregated_value']}")
    """
    
    # Default property sets to search if not specified
    if property_sets is None:
        property_sets = [
            'PSet_Revit_Dimensions',
            'Pset_WallCommon',
            'Qto_WallBaseQuantities',
            'Qto_SlabBaseQuantities',
            'Qto_FootingBaseQuantities'
        ]
    
    try:
        # Get all elements of specified types
        all_elements = []
        for element_type in element_types:
            try:
                elements = ifc_file.by_type(element_type)
                all_elements.extend(elements)
            except Exception as e:
                print(f"Warning: Could not get elements of type {element_type}: {e}")
                continue
        
        # Filter elements by keywords
        matching_elements = []
        exclude_keywords = exclude_keywords or []
        
        for element in all_elements:
            # Get values from search fields
            field_values = []
            for field in search_fields:
                if hasattr(element, field):
                    value = getattr(element, field)
                    if value:
                        field_values.append(str(value))
            
            # Combine all field values for searching
            combined_text = ' '.join(field_values)
            
            if not case_sensitive:
                combined_text = combined_text.lower()
                include_keywords_lower = [kw.lower() for kw in include_keywords]
                exclude_keywords_lower = [kw.lower() for kw in exclude_keywords]
            else:
                include_keywords_lower = include_keywords
                exclude_keywords_lower = exclude_keywords
            
            # Check include keywords
            include_match = any(kw in combined_text for kw in include_keywords_lower)
            
            # Check exclude keywords
            exclude_match = any(kw in combined_text for kw in exclude_keywords_lower)
            
            if include_match and not exclude_match:
                matching_elements.append(element)
        
        # Extract quantities from matching elements
        element_details = []
        quantity_values = []
        
        for element in matching_elements:
            element_info = {
                'id': element.id(),
                'type': element.is_a(),
                'name': getattr(element, 'Name', ''),
                'object_type': getattr(element, 'ObjectType', '')
            }
            
            # Get property sets for this element
            psets = ifcopenshell.util.element.get_psets(element)
            quantity_value = None
            quantity_source = None
            
            # Search for the quantity property in specified property sets
            for pset_name in property_sets:
                if pset_name in psets:
                    properties = psets[pset_name]
                    for prop_name, prop_value in properties.items():
                        # Check if property name matches the quantity we're looking for
                        if (quantity_property.lower() in prop_name.lower() or 
                            prop_name.lower() in quantity_property.lower()):
                            if isinstance(prop_value, (int, float)):
                                quantity_value = float(prop_value)
                                quantity_source = f"{pset_name}.{prop_name}"
                                break
                    if quantity_value is not None:
                        break
            
            # If not found in specified property sets, search all property sets
            if quantity_value is None:
                for pset_name, properties in psets.items():
                    for prop_name, prop_value in properties.items():
                        if (quantity_property.lower() in prop_name.lower() or 
                            prop_name.lower() in quantity_property.lower()):
                            if isinstance(prop_value, (int, float)):
                                quantity_value = float(prop_value)
                                quantity_source = f"{pset_name}.{prop_name}"
                                break
                    if quantity_value is not None:
                        break
            
            element_info['quantity_value'] = quantity_value
            element_info['quantity_source'] = quantity_source
            element_details.append(element_info)
            
            if quantity_value is not None:
                quantity_values.append(quantity_value)
        
        # Aggregate the results
        if not quantity_values:
            aggregated_value = 0.0
        else:
            if aggregation == 'sum':
                aggregated_value = sum(quantity_values)
            elif aggregation == 'average':
                aggregated_value = sum(quantity_values) / len(quantity_values)
            elif aggregation == 'count':
                aggregated_value = len(quantity_values)
            elif aggregation == 'max':
                aggregated_value = max(quantity_values)
            elif aggregation == 'min':
                aggregated_value = min(quantity_values)
            else:
                aggregated_value = sum(quantity_values)  # Default to sum
        
        # Prepare result
        result = {
            'aggregated_value': aggregated_value,
            'count': len(matching_elements),
            'elements_with_quantities': len(quantity_values)
        }
        
        if include_details:
            result['elements'] = element_details
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'aggregated_value': 0.0,
            'count': 0,
            'elements_with_quantities': 0
        }