import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Set, Any, Optional, Union

def find_elements_with_property_by_type(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_set_name: Optional[str] = None,
    property_name: Optional[str] = None,
    categorize_by: str = 'ObjectType',
    include_property_values: bool = True,
    property_names: Optional[List[str]] = None,
    property_sets: Optional[List[str]] = None,
    search_mode: str = 'any'
) -> Dict[str, Any]:
    """
    Finds IFC elements of a specified type that contain specific properties and categorizes them by their types.
    
    This function answers questions like 'which door types include fire rating information?' by checking
    for property existence rather than exact value matching. It handles the common pattern of property set
    iteration, safe property access, and type-based categorization.
    
    Enhanced to support multiple property names and property sets in a single call for comprehensive
    domain-specific property searches like fire safety, thermal performance, or acoustic properties.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcDoor', 'IfcWall', 'IfcWindow')
        property_set_name: Name of the property set to check (for backward compatibility)
        property_name: Name of the property to check for existence (for backward compatibility)
        categorize_by: Field to categorize elements by (default: 'ObjectType', options: 'ObjectType', 'Name')
        include_property_values: Whether to extract actual property values (default: True)
        property_names: List of property names to search for (new functionality)
        property_sets: List of property set names to search in (new functionality)
        search_mode: Search mode - 'any' to match any property, 'all' to match all properties (default: 'any')
    
    Returns:
        Dict with:
        - 'elements_with_property': List of elements that have the property/properties
        - 'types_with_property': Dict mapping element types to sets of property values found
        - 'summary': Dict with counts and statistics
        - 'search_details': Dict with information about what was searched
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> # Old usage (backward compatible)
        >>> result = find_elements_with_property_by_type(
        ...     ifc_file=model,
        ...     element_type='IfcDoor',
        ...     property_set_name='Pset_DoorCommon',
        ...     property_name='FireRating'
        ... )
        >>> # New usage (multiple properties)
        >>> result = find_elements_with_property_by_type(
        ...     ifc_file=model,
        ...     element_type='IfcDoor',
        ...     property_names=['FireRating', 'FireExit'],
        ...     property_sets=['Pset_DoorCommon', 'Pset_FireSafety'],
        ...     search_mode='any'
        ... )
    """
    
    try:
        # Validate inputs
        if not isinstance(ifc_file, ifcopenshell.file):
            raise ValueError("ifc_file must be a valid ifcopenshell.file object")
        
        if not element_type or not isinstance(element_type, str):
            raise ValueError("element_type must be a non-empty string")
        
        if categorize_by not in ['ObjectType', 'Name']:
            raise ValueError("categorize_by must be either 'ObjectType' or 'Name'")
        
        if search_mode not in ['any', 'all']:
            raise ValueError("search_mode must be either 'any' or 'all'")
        
        # Handle backward compatibility and new functionality
        if property_names is None and property_sets is None:
            # Old usage - use single property_set_name and property_name
            if property_set_name is None or property_name is None:
                raise ValueError("Either property_set_name and property_name must be provided (old usage), or property_names and/or property_sets must be provided (new usage)")
            property_names_list = [property_name]
            property_sets_list = [property_set_name]
            is_legacy_mode = True
        else:
            # New usage - use property_names and/or property_sets
            if property_names is None:
                property_names_list = []  # Search all properties in specified sets
            else:
                property_names_list = property_names
            
            if property_sets is None:
                property_sets_list = []  # Search specified properties in all sets
            else:
                property_sets_list = property_sets
            
            is_legacy_mode = False
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Initialize results
        elements_with_property = []
        types_with_property: Dict[str, Set[str]] = {}
        all_types: Set[str] = set()
        search_details = {
            'property_names_searched': property_names_list,
            'property_sets_searched': property_sets_list,
            'search_mode': search_mode,
            'is_legacy_mode': is_legacy_mode
        }
        
        # Process each element
        for element in elements:
            # Get the categorization value
            if categorize_by == 'ObjectType':
                element_type_name = getattr(element, 'ObjectType', None) or getattr(element, 'Name', 'Unknown')
            else:  # categorize_by == 'Name'
                element_type_name = getattr(element, 'Name', 'Unknown')
            
            all_types.add(element_type_name)
            
            # Get all property sets for this element
            all_psets = ifcopenshell.util.element.get_psets(element)
            
            # Track found properties for this element
            found_properties = []
            found_property_values = {}
            
            # Search through property sets and properties
            for pset_name, pset_properties in all_psets.items():
                # Check if we should search this property set
                if property_sets_list and pset_name not in property_sets_list:
                    continue
                
                # Check properties in this set
                for prop_name, prop_value in pset_properties.items():
                    # Check if we should search this property
                    if property_names_list and prop_name not in property_names_list:
                        continue
                    
                    # Property found
                    found_properties.append(f"{pset_name}.{prop_name}")
                    if include_property_values:
                        found_property_values[f"{pset_name}.{prop_name}"] = prop_value
            
            # Determine if element matches search criteria
            element_matches = False
            if search_mode == 'any' and found_properties:
                element_matches = True
            elif search_mode == 'all':
                # For 'all' mode, we need to check if all specified properties were found
                if is_legacy_mode:
                    # Legacy mode: check if the single property was found
                    element_matches = len(found_properties) > 0
                else:
                    # New mode: check if all specified combinations were found
                    required_combinations = []
                    if property_names_list and property_sets_list:
                        # Both specified: check all combinations
                        for pset in property_sets_list:
                            for prop in property_names_list:
                                required_combinations.append(f"{pset}.{prop}")
                    elif property_names_list:
                        # Only properties specified: check in any set
                        for prop in property_names_list:
                            required_combinations.append(prop)
                    elif property_sets_list:
                        # Only sets specified: check any property in these sets
                        for pset in property_sets_list:
                            required_combinations.append(pset)
                    
                    if not required_combinations:
                        # No specific requirements, match if any property found
                        element_matches = len(found_properties) > 0
                    else:
                        # Check if all required combinations are found
                        found_combinations = set(found_properties)
                        element_matches = all(req in found_combinations for req in required_combinations)
            
            if element_matches:
                # Element has the property/properties
                element_info = {
                    'GlobalId': getattr(element, 'GlobalId', None),
                    'Name': getattr(element, 'Name', None),
                    'ObjectType': getattr(element, 'ObjectType', None),
                    'Type': element_type_name
                }
                
                if include_property_values:
                    element_info['properties'] = found_property_values
                
                elements_with_property.append(element_info)
                
                # Add to types categorization
                if element_type_name not in types_with_property:
                    types_with_property[element_type_name] = set()
                
                if include_property_values:
                    for prop_path, value in found_property_values.items():
                        types_with_property[element_type_name].add(f"{prop_path}={value}")
                else:
                    types_with_property[element_type_name].add('Has Properties')
        
        # Create summary
        summary = {
            'total_elements': len(elements),
            'elements_with_property': len(elements_with_property),
            'total_types': len(all_types),
            'types_with_property': len(types_with_property),
            'element_type': element_type,
            'search_mode': search_mode
        }
        
        if is_legacy_mode:
            summary['property_set_name'] = property_set_name
            summary['property_name'] = property_name
        else:
            summary['property_names'] = property_names_list
            summary['property_sets'] = property_sets_list
        
        # Convert sets to sorted lists for better serialization
        types_with_property_serializable = {
            type_name: sorted(list(values)) 
            for type_name, values in types_with_property.items()
        }
        
        return {
            'elements_with_property': elements_with_property,
            'types_with_property': types_with_property_serializable,
            'summary': summary,
            'search_details': search_details
        }
        
    except Exception as e:
        # Return error information in a structured way
        return {
            'elements_with_property': [],
            'types_with_property': {},
            'summary': {
                'error': str(e),
                'element_type': element_type,
                'search_mode': search_mode
            },
            'search_details': {
                'error': str(e)
            }
        }