import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Set, Any, Optional, Union

def find_elements_with_property_by_type(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_set_name: str,
    property_name: str,
    categorize_by: str = 'ObjectType',
    include_property_values: bool = True
) -> Dict[str, Any]:
    """
    Finds IFC elements of a specified type that contain a specific property and categorizes them by their types.
    
    This function answers questions like 'which door types include fire rating information?' by checking
    for property existence rather than exact value matching. It handles the common pattern of property set
    iteration, safe property access, and type-based categorization.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcDoor', 'IfcWall', 'IfcWindow')
        property_set_name: Name of the property set to check (e.g., 'Pset_DoorCommon')
        property_name: Name of the property to check for existence (e.g., 'FireRating')
        categorize_by: Field to categorize elements by (default: 'ObjectType', options: 'ObjectType', 'Name')
        include_property_values: Whether to extract actual property values (default: True)
    
    Returns:
        Dict with:
        - 'elements_with_property': List of elements that have the property
        - 'types_with_property': Dict mapping element types to sets of property values found
        - 'summary': Dict with counts and statistics
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = find_elements_with_property_by_type(
        ...     ifc_file=model,
        ...     element_type='IfcDoor',
        ...     property_set_name='Pset_DoorCommon',
        ...     property_name='FireRating'
        ... )
        >>> print(result['types_with_property'])
        {'Door Type A': {'EI 30'}, 'Door Type B': {'EI 60'}}
    """
    
    try:
        # Validate inputs
        if not isinstance(ifc_file, ifcopenshell.file):
            raise ValueError("ifc_file must be a valid ifcopenshell.file object")
        
        if not element_type or not isinstance(element_type, str):
            raise ValueError("element_type must be a non-empty string")
        
        if not property_set_name or not isinstance(property_set_name, str):
            raise ValueError("property_set_name must be a non-empty string")
        
        if not property_name or not isinstance(property_name, str):
            raise ValueError("property_name must be a non-empty string")
        
        if categorize_by not in ['ObjectType', 'Name']:
            raise ValueError("categorize_by must be either 'ObjectType' or 'Name'")
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Initialize results
        elements_with_property = []
        types_with_property: Dict[str, Set[str]] = {}
        all_types: Set[str] = set()
        
        # Process each element
        for element in elements:
            # Get the categorization value
            if categorize_by == 'ObjectType':
                element_type_name = getattr(element, 'ObjectType', None) or getattr(element, 'Name', 'Unknown')
            else:  # categorize_by == 'Name'
                element_type_name = getattr(element, 'Name', 'Unknown')
            
            all_types.add(element_type_name)
            
            # Check if the element has the specified property
            property_value = ifcopenshell.util.element.get_pset(
                element, property_set_name, property_name
            )
            
            if property_value is not None:
                # Element has the property
                element_info = {
                    'GlobalId': getattr(element, 'GlobalId', None),
                    'Name': getattr(element, 'Name', None),
                    'ObjectType': getattr(element, 'ObjectType', None),
                    'Type': element_type_name
                }
                
                if include_property_values:
                    element_info[property_name] = property_value
                
                elements_with_property.append(element_info)
                
                # Add to types categorization
                if element_type_name not in types_with_property:
                    types_with_property[element_type_name] = set()
                
                if include_property_values:
                    types_with_property[element_type_name].add(str(property_value))
                else:
                    types_with_property[element_type_name].add('Has Property')
        
        # Create summary
        summary = {
            'total_elements': len(elements),
            'elements_with_property': len(elements_with_property),
            'total_types': len(all_types),
            'types_with_property': len(types_with_property),
            'property_set_name': property_set_name,
            'property_name': property_name,
            'element_type': element_type
        }
        
        # Convert sets to sorted lists for better serialization
        types_with_property_serializable = {
            type_name: sorted(list(values)) 
            for type_name, values in types_with_property.items()
        }
        
        return {
            'elements_with_property': elements_with_property,
            'types_with_property': types_with_property_serializable,
            'summary': summary
        }
        
    except Exception as e:
        # Return error information in a structured way
        return {
            'elements_with_property': [],
            'types_with_property': {},
            'summary': {
                'error': str(e),
                'element_type': element_type,
                'property_set_name': property_set_name,
                'property_name': property_name
            }
        }