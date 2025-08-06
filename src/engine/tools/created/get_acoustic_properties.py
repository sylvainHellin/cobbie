import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *


def get_acoustic_properties(
    ifc_file_path: str,
    element_types: List[str] = None,
    acoustic_property_names: List[str] = None,
    search_property_sets: bool = True
) -> Dict[str, Any]:
    """
    Retrieve acoustic properties from IFC models, focusing on STC ratings and other acoustic performance metrics.
    
    This function searches for acoustic properties in building elements such as walls, doors, floors, and ceilings.
    It looks for properties like Sound Transmission Class (STC) ratings, sound insulation values, and other 
    acoustic performance metrics in element property sets.
    
    The function handles various IFC schema versions and different BIM authoring software conventions for 
    storing acoustic properties. Common property set names that may contain acoustic information include:
    - Pset_WallCommon
    - Pset_DoorCommon
    - Pset_WindowCommon
    - Pset_Flooring
    - Pset_Ceiling
    - Pset_Acoustic
    - Pset_AcousticalCeiling
    - Pset_AcousticalFurniture
    - Pset_AudioVisual
    
    Assumptions:
    - Acoustic properties are stored in property sets rather than as explicit IFC attributes
    - Property names follow common naming conventions (e.g., STC, AcousticRating, SoundTransmissionClass)
    - The IFC file contains building elements with associated property sets
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_types (List[str], optional): List of IFC element types to search within 
            (e.g., ['IfcWall', 'IfcDoor', 'IfcSlab']). If None, search common building element types.
        acoustic_property_names (List[str], optional): List of specific acoustic property names to look for 
            (e.g., ['STC', 'SoundTransmissionClass', 'AcousticInsulation']). If None, search for common acoustic property names.
        search_property_sets (bool): Whether to search within property sets for acoustic properties. Defaults to True.
        
    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'found_properties': List of dictionaries with acoustic properties found
            - 'elements_without_acoustic_data': List of element GUIDs that were checked but had no acoustic properties
            - 'summary': Summary statistics
            - 'recommendations': Suggestions for finding acoustic information
            
    Example:
        >>> result = get_acoustic_properties("model.ifc")
        >>> print(f"Found {len(result['found_properties'])} acoustic properties")
    """
    # Common acoustic property names to search for if none are specified
    common_acoustic_properties = [
        'STC', 'SoundTransmissionClass', 'AcousticInsulation', 'AcousticRating',
        'STCRating', 'ImpactSoundRating', 'AirborneSoundRating', 'SoundAbsorption',
        'SoundInsulation', 'NoiseRating', 'IIC', 'NRC', 'SoundReductionIndex'
    ]
    
    # Use provided property names or default to common ones
    search_properties = acoustic_property_names if acoustic_property_names else common_acoustic_properties
    
    # Open the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Get elements to search based on element_types parameter
    if element_types:
        elements = []
        for element_type in element_types:
            elements.extend(ifc_file.by_type(element_type))
    else:
        # If no specific element types provided, search common building elements
        building_element_types = [
            'IfcWall', 'IfcDoor', 'IfcWindow', 'IfcSlab', 'IfcRoof', 
            'IfcCeiling', 'IfcFloor', 'IfcCurtainWall'
        ]
        elements = []
        for element_type in building_element_types:
            elements.extend(ifc_file.by_type(element_type))
    
    # Initialize results
    found_properties = []
    elements_without_acoustic_data = []
    
    # Process each element
    for element in elements:
        element_has_acoustic_data = False
        element_name = getattr(element, 'Name', 'Unnamed')
        element_guid = getattr(element, 'GlobalId', 'Unknown')
        element_type = element.is_a()
        
        # Get property sets if search_property_sets is True
        if search_property_sets:
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                # Search through property sets for acoustic properties
                for pset_name, properties in psets.items():
                    # Skip the 'id' key which is not a property set
                    if pset_name == 'id':
                        continue
                    
                    for prop_name, prop_value in properties.items():
                        # Check if property name matches any of our search terms (case insensitive)
                        if any(acoustic_term.lower() in prop_name.lower() for acoustic_term in search_properties):
                            element_has_acoustic_data = True
                            # Try to get unit information if available
                            unit = None
                            # Note: Extracting unit information would require more complex processing
                            # of the IFC schema which is beyond the scope of this implementation
                            
                            found_properties.append({
                                'element_name': element_name,
                                'element_guid': element_guid,
                                'element_type': element_type,
                                'property_set_name': pset_name,
                                'property_name': prop_name,
                                'property_value': prop_value,
                                'unit': unit
                            })
            except Exception as e:
                # Handle cases where property set extraction fails
                pass
        
        # If no acoustic data was found for this element, add to the list
        if not element_has_acoustic_data:
            elements_without_acoustic_data.append(element_guid)
    
    # Create summary
    summary = {
        'total_elements_checked': len(elements),
        'elements_with_acoustic_data': len(found_properties),
        'property_sets_searched': search_property_sets,
        'common_acoustic_properties_searched': search_properties
    }
    
    # Create recommendations
    recommendations = []
    if len(found_properties) == 0:
        recommendations.append("No acoustic properties found in the model. Consider checking if the model contains acoustic information or if it was exported with property sets included.")
        recommendations.append("Acoustic data might be stored in external documents or specifications rather than in the IFC model itself.")
        recommendations.append("Check with the model author to ensure acoustic properties were included during export.")
        recommendations.append("Try expanding the search to include more element types or custom property names.")
    else:
        recommendations.append("Acoustic properties found successfully. Review the 'found_properties' list for details.")
        recommendations.append("Consider verifying the values with the project specifications as property values may not always reflect the latest design information.")
    
    return {
        'found_properties': found_properties,
        'elements_without_acoustic_data': elements_without_acoustic_data,
        'summary': summary,
        'recommendations': recommendations
    }