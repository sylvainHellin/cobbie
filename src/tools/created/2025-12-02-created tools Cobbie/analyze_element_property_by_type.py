import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any

def analyze_element_property_by_type(
    ifc_file,
    element_type: str,
    filter_keywords: List[str],
    property_set_name: str,
    property_name: str,
    case_sensitive: bool = False,
    group_by_field: str = 'ObjectType',
    max_elements: int = 1000
) -> Dict[str, Any]:
    """
    Analyzes a specific property across IFC elements filtered by type and keywords,
    providing aggregated results grouped by element type.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcDoor')
        filter_keywords: List of keywords to filter elements (searched in ObjectType and Name)
        property_set_name: Name of the property set containing the target property
        property_name: Name of the property to analyze
        case_sensitive: Whether keyword matching is case sensitive (default False)
        group_by_field: Field to group results by ('ObjectType', 'Name', or 'Description')
        max_elements: Maximum elements to analyze (default 1000)
    
    Returns:
        Dict containing:
        - total_elements: Total number of elements matching filter criteria
        - property_values: Dict mapping property values to counts and percentages
        - type_breakdown: Dict showing property value distribution for each element type
        - examples: Sample elements for each property value
        
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = analyze_element_property_by_type(
        ...     ifc_file=model,
        ...     element_type='IfcWall',
        ...     filter_keywords=['interior'],
        ...     property_set_name='Pset_WallCommon',
        ...     property_name='LoadBearing'
        ... )
        >>> print(f"Found {result['total_elements']} interior walls")
        >>> print(f"Load bearing distribution: {result['property_values']}")
    """
    try:
        # Initialize result structure
        result = {
            'total_elements': 0,
            'property_values': {},
            'type_breakdown': {},
            'examples': {}
        }
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Filter elements by keywords
        filtered_elements = []
        for element in elements[:max_elements]:
            if not case_sensitive:
                search_text = ''
                if hasattr(element, 'ObjectType') and element.ObjectType:
                    search_text += element.ObjectType.lower()
                if hasattr(element, 'Name') and element.Name:
                    search_text += ' ' + element.Name.lower()
                
                if any(keyword.lower() in search_text for keyword in filter_keywords):
                    filtered_elements.append(element)
            else:
                search_text = ''
                if hasattr(element, 'ObjectType') and element.ObjectType:
                    search_text += element.ObjectType
                if hasattr(element, 'Name') and element.Name:
                    search_text += ' ' + element.Name
                
                if any(keyword in search_text for keyword in filter_keywords):
                    filtered_elements.append(element)
        
        result['total_elements'] = len(filtered_elements)
        
        if not filtered_elements:
            return result
        
        # Analyze property values for filtered elements
        for element in filtered_elements:
            # Get the group field value
            group_value = 'Unknown'
            if group_by_field == 'ObjectType' and hasattr(element, 'ObjectType') and element.ObjectType:
                group_value = element.ObjectType
            elif group_by_field == 'Name' and hasattr(element, 'Name') and element.Name:
                group_value = element.Name
            elif group_by_field == 'Description' and hasattr(element, 'Description') and element.Description:
                group_value = str(element.Description)
            
            # Initialize group in type_breakdown if not exists
            if group_value not in result['type_breakdown']:
                result['type_breakdown'][group_value] = {}
            
            # Get property value
            try:
                property_value = ifcopenshell.util.element.get_pset(element, property_set_name, property_name)
            except:
                property_value = None
            
            # Convert property value to string for dictionary keys
            prop_key = str(property_value) if property_value is not None else 'None'
            
            # Update property values count
            if prop_key not in result['property_values']:
                result['property_values'][prop_key] = {'count': 0, 'percentage': 0.0}
            result['property_values'][prop_key]['count'] += 1
            
            # Update type breakdown
            if prop_key not in result['type_breakdown'][group_value]:
                result['type_breakdown'][group_value][prop_key] = 0
            result['type_breakdown'][group_value][prop_key] += 1
            
            # Store examples (first 3 for each property value)
            if prop_key not in result['examples']:
                result['examples'][prop_key] = []
            if len(result['examples'][prop_key]) < 3:
                result['examples'][prop_key].append({
                    'id': element.id(),
                    'name': element.Name if hasattr(element, 'Name') else '',
                    'object_type': element.ObjectType if hasattr(element, 'ObjectType') else '',
                    'group_field': group_value
                })
        
        # Calculate percentages
        for prop_key in result['property_values']:
            result['property_values'][prop_key]['percentage'] = (
                result['property_values'][prop_key]['count'] / result['total_elements'] * 100
            )
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'total_elements': 0,
            'property_values': {},
            'type_breakdown': {},
            'examples': {}
        }