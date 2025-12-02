import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any, Union

def classify_elements_by_type_and_count(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_sets_to_extract: Optional[List[str]] = None,
    properties_to_extract: Optional[List[str]] = None,
    max_examples_per_type: int = 3,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Classifies IFC elements by their ObjectType and type definitions, then counts them by type with optional property extraction.
    
    This function handles the common BIM analysis task of understanding element type distribution in a model.
    It analyzes elements by their ObjectType attribute and IsTypedBy relationships to determine classification,
    then provides counts and detailed examples for each type.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcDoor', 'IfcWindow')
        property_sets_to_extract: Optional list of property set names to extract for examples
            (default: ['Pset_WallCommon', 'Dimensions', 'Pset_DoorCommon', 'Pset_WindowCommon'])
        properties_to_extract: Optional list of specific property names to extract
            (default: ['IsExternal', 'LoadBearing', 'Area', 'Length', 'Volume', 'Height', 'Width'])
        max_examples_per_type: Maximum number of example elements to analyze per type (default: 3)
        case_sensitive: Whether string matching should be case sensitive (default: False)
    
    Returns:
        Dict containing:
        - 'total_elements': Total number of elements found
        - 'type_counts': Dict mapping type names to element counts
        - 'type_details': Dict mapping type names to list of example element details
        - 'untyped_elements': Count of elements without ObjectType or type definition
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = classify_elements_by_type_and_count(model, 'IfcWall')
        >>> print(f"Total walls: {result['total_elements']}")
        >>> for wall_type, count in result['type_counts'].items():
        ...     print(f"{wall_type}: {count}")
    """
    # Set default values
    if property_sets_to_extract is None:
        property_sets_to_extract = ['Pset_WallCommon', 'Dimensions', 'Pset_DoorCommon', 'Pset_WindowCommon']
    if properties_to_extract is None:
        properties_to_extract = ['IsExternal', 'LoadBearing', 'Area', 'Length', 'Volume', 'Height', 'Width']
    
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_elements = len(elements)
        
        if total_elements == 0:
            return {
                'total_elements': 0,
                'type_counts': {},
                'type_details': {},
                'untyped_elements': 0
            }
        
        # Initialize data structures
        type_counts: Dict[str, int] = {}
        type_details: Dict[str, List[Dict[str, Any]]] = {}
        untyped_count = 0
        
        for element in elements:
            # Determine the type name
            type_name = None
            
            # First try to get type from IsTypedBy relationship
            try:
                element_type_obj = ifcopenshell.util.element.get_type(element)
                if element_type_obj and hasattr(element_type_obj, 'Name') and element_type_obj.Name:
                    type_name = element_type_obj.Name
            except:
                pass
            
            # If no type found, try ObjectType attribute
            if not type_name:
                if hasattr(element, 'ObjectType') and element.ObjectType:
                    type_name = element.ObjectType
            
            # If still no type, mark as untyped
            if not type_name:
                untyped_count += 1
                type_name = 'Untyped'
            
            # Apply case sensitivity
            if not case_sensitive:
                type_name = type_name.lower() if type_name else 'untyped'
            
            # Count the element
            if type_name not in type_counts:
                type_counts[type_name] = 0
                type_details[type_name] = []
            type_counts[type_name] += 1
            
            # Extract details for examples (limit to max_examples_per_type)
            if len(type_details[type_name]) < max_examples_per_type:
                element_details = {
                    'Name': getattr(element, 'Name', None),
                    'ObjectType': getattr(element, 'ObjectType', None),
                    'GlobalId': getattr(element, 'GlobalId', None),
                    'id': element.id()
                }
                
                # Extract properties from property sets
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    
                    for pset_name in property_sets_to_extract:
                        if pset_name in psets:
                            pset_data = psets[pset_name]
                            for prop_name in properties_to_extract:
                                if prop_name in pset_data:
                                    element_details[prop_name] = psets[pset_name][prop_name]
                except:
                    # Fallback to manual property extraction if get_psets fails
                    try:
                        if hasattr(element, 'IsDefinedBy'):
                            for rel in element.IsDefinedBy:
                                if hasattr(rel, 'RelatingPropertyDefinition'):
                                    prop_def = rel.RelatingPropertyDefinition
                                    if hasattr(prop_def, 'Name') and prop_def.Name in property_sets_to_extract:
                                        if hasattr(prop_def, 'HasProperties'):
                                            for prop in prop_def.HasProperties:
                                                if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                                    if prop.Name in properties_to_extract:
                                                        element_details[prop.Name] = prop.NominalValue.wrappedValue
                    except:
                        pass
                
                type_details[type_name].append(element_details)
        
        return {
            'total_elements': total_elements,
            'type_counts': type_counts,
            'type_details': type_details,
            'untyped_elements': untyped_count
        }
        
    except Exception as e:
        # Return error information
        return {
            'total_elements': 0,
            'type_counts': {},
            'type_details': {},
            'untyped_elements': 0,
            'error': str(e)
        }