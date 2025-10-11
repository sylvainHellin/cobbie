import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union


def get_door_properties_by_guid(
    model_path: str,
    guid: str,
    property_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Extract door properties by GlobalId with comprehensive property set navigation.
    
    This function searches through all relevant property sets to find door properties,
    standardizes property names and values, and provides source information for auditability.
    
    Args:
        model_path: Path to the IFC model file
        guid: GlobalId of the door element
        property_names: Optional list of specific properties to retrieve.
                     If None, returns all common door properties.
                     Examples: ['Width', 'Height', 'FireRating', 'Thickness']
    
    Returns:
        Dict containing:
        - element_name: Name of the door
        - element_guid: GlobalId of the door
        - properties: Dictionary of standardized properties
        - property_sources: Information about which property sets each value came from
        - confidence_level: Confidence in extracted values (high/medium/low)
    
    Note:
        This function handles property sets commonly found in Revit-exported IFC models,
        including PSet_Revit_Type_Dimensions, Pset_DoorCommon, and other Revit-specific
        property sets. Property names are standardized to common conventions.
    """
    
    # Load the IFC model
    try:
        model = ifcopenshell.open(model_path)
    except Exception as e:
        return {
            'element_name': None,
            'element_guid': guid,
            'properties': {},
            'property_sources': {'error': f'Failed to load model: {str(e)}'},
            'confidence_level': 'low'
        }
    
    # Find the door by GUID
    door = model.by_guid(guid)
    if not door or not door.is_a('IfcDoor'):
        return {
            'element_name': None,
            'element_guid': guid,
            'properties': {},
            'property_sources': {'error': f'Door with GUID {guid} not found or not an IfcDoor'},
            'confidence_level': 'low'
        }
    
    # Initialize result structure
    result = {
        'element_name': door.Name,
        'element_guid': guid,
        'properties': {},
        'property_sources': {},
        'confidence_level': 'high'
    }
    
    # Define property mapping for standardization
    # Maps standard property names to possible sources and their corresponding property names
    property_mapping = {
        'width': {
            'direct': [('OverallWidth', 'direct_attribute')],
            'psets': [
                ('PSet_Revit_Type_Dimensions', 'Width'),
                ('PSet_Revit_Type_Other', 'NominalWidth')
            ]
        },
        'height': {
            'direct': [('OverallHeight', 'direct_attribute')],
            'psets': [
                ('PSet_Revit_Type_Dimensions', 'Height'),
                ('PSet_Revit_Other', 'Head Height'),
                ('PSet_Revit_Type_Other', 'NominalHeight')
            ]
        },
        'thickness': {
            'direct': [],
            'psets': [
                ('PSet_Revit_Type_Dimensions', 'Thickness')
            ]
        },
        'fire_rating': {
            'direct': [],
            'psets': [
                ('Pset_DoorCommon', 'FireRating'),
                ('PSet_Revit_Type_Identity Data', 'Fire Rating')
            ]
        },
        'is_external': {
            'direct': [],
            'psets': [
                ('Pset_DoorCommon', 'IsExternal')
            ]
        },
        'reference': {
            'direct': [],
            'psets': [
                ('Pset_DoorCommon', 'Reference'),
                ('PSet_Revit_Type_Other', 'Reference')
            ]
        },
        'level': {
            'direct': [],
            'psets': [
                ('PSet_Revit_Constraints', 'Level')
            ]
        },
        'sill_height': {
            'direct': [],
            'psets': [
                ('PSet_Revit_Constraints', 'Sill Height')
            ]
        },
        'door_material': {
            'direct': [],
            'psets': [
                ('PSet_Revit_Type_Materials and Finishes', 'Door Material')
            ]
        },
        'frame_material': {
            'direct': [],
            'psets': [
                ('PSet_Revit_Type_Materials and Finishes', 'Frame Material')
            ]
        }
    }
    
    # Determine which properties to search for
    if property_names is None:
        properties_to_find = list(property_mapping.keys())
    else:
        properties_to_find = [prop.lower() for prop in property_names]
    
    # Collect all property sets from the door
    property_sets = {}
    for rel in door.IsDefinedBy:
        if rel.is_a('IfcRelDefinesByProperties'):
            pset = rel.RelatingPropertyDefinition
            if hasattr(pset, 'HasProperties'):
                properties = {}
                for prop in pset.HasProperties:
                    if prop.is_a('IfcPropertySingleValue'):
                        value = prop.NominalValue.wrappedValue if prop.NominalValue else None
                        properties[prop.Name] = value
                    elif prop.is_a('IfcPropertyEnumeratedValue'):
                        values = [v.wrappedValue for v in prop.EnumerationValues] if prop.EnumerationValues else []
                        properties[prop.Name] = values
                property_sets[pset.Name] = properties
    
    # Extract properties for each requested property
    found_properties = 0
    total_properties = len(properties_to_find)
    
    for prop_name in properties_to_find:
        if prop_name not in property_mapping:
            result['properties'][prop_name] = None
            result['property_sources'][prop_name] = {'source': 'unknown', 'note': 'Property not in mapping'}
            continue
        
        mapping = property_mapping[prop_name]
        found_value = None
        found_source = None
        
        # Check direct attributes first (highest priority)
        for attr_name, source_type in mapping['direct']:
            if hasattr(door, attr_name):
                value = getattr(door, attr_name)
                if value is not None:
                    found_value = value
                    found_source = source_type
                    break
        
        # If not found in direct attributes, check property sets
        if found_value is None:
            for pset_name, prop_name_in_pset in mapping['psets']:
                if pset_name in property_sets and prop_name_in_pset in property_sets[pset_name]:
                    value = property_sets[pset_name][prop_name_in_pset]
                    if value is not None:
                        found_value = value
                        found_source = f'{pset_name}.{prop_name_in_pset}'
                        break
        
        # Store the result
        if found_value is not None:
            result['properties'][prop_name] = found_value
            result['property_sources'][prop_name] = {'source': found_source, 'value': found_value}
            found_properties += 1
        else:
            result['properties'][prop_name] = None
            result['property_sources'][prop_name] = {'source': 'not_found', 'note': 'Property not found in any source'}
    
    # Calculate confidence level
    if found_properties == 0:
        result['confidence_level'] = 'low'
    elif found_properties < total_properties * 0.5:
        result['confidence_level'] = 'medium'
    else:
        result['confidence_level'] = 'high'
    
    return result