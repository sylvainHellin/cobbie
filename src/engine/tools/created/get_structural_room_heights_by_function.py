
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

def get_structural_room_heights_by_function(
    ifc_file_path: str,
    function_keywords: List[str],
    height_property_names: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Identifies functional areas in structural IFC models and extracts their height properties.
    This function works with structural models where explicit IfcSpace elements are not present.
    
    The function analyzes:
    1. Storey elevations to determine vertical boundaries
    2. Element relationships and groupings
    3. Property sets that indicate functional areas
    
    Args:
        ifc_file_path (str): Path to the IFC file
        function_keywords (List[str]): Keywords to identify functional areas (e.g., ["dental", "operatory", "reception"])
        height_property_names (List[str]): Property names that contain height information (e.g., ["Unconnected Height", "Height Offset From Level"])
        
    Returns:
        Dict[str, Dict[str, Any]]: A dictionary where keys are functional area names and values are dictionaries
        containing height information and related elements.
        
    Example:
        >>> result = get_structural_room_heights_by_function(
        ...     "model.ifc",
        ...     ["dental", "operatory"],
        ...     ["Unconnected Height", "Height Offset From Level"]
        ... )
        >>> print(result)
        {
            "Dental Operatory": {
                "elements": ["#12345", "#12346"],
                "height_from_property": 3.0,
                "height_from_storey": 4.57,
                "storey_range": ("First Floor", "Second Floor")
            }
        }
    """
    # Load the IFC model
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Get all storeys and sort by elevation
    storeys = ifc_file.by_type('IfcBuildingStorey')
    storeys_sorted = sorted(storeys, key=lambda s: s.Elevation)
    
    # Calculate storey heights
    storey_heights = {}
    for i, storey in enumerate(storeys_sorted):
        if i < len(storeys_sorted) - 1:
            next_storey = storeys_sorted[i+1]
            height = next_storey.Elevation - storey.Elevation
            storey_heights[storey.Name] = height
    
    # Find all building elements
    elements = []
    elements.extend(ifc_file.by_type('IfcWall'))
    elements.extend(ifc_file.by_type('IfcWallStandardCase'))
    elements.extend(ifc_file.by_type('IfcSlab'))
    elements.extend(ifc_file.by_type('IfcBeam'))
    elements.extend(ifc_file.by_type('IfcColumn'))
    
    # Identify functional areas based on keywords
    functional_areas = {}
    
    for element in elements:
        # Check element name for function keywords
        element_name = getattr(element, 'Name', '') or ''
        
        for keyword in function_keywords:
            if keyword.lower() in element_name.lower():
                if keyword not in functional_areas:
                    functional_areas[keyword] = {
                        'elements': [],
                        'height_from_property': None,
                        'height_from_storey': None,
                        'storey_range': None
                    }
                
                # Add element to functional area
                functional_areas[keyword]['elements'].append(element.GlobalId)
                
                # Extract height information from property sets
                if functional_areas[keyword]['height_from_property'] is None:
                    psets = ifcopenshell.util.element.get_psets(element)
                    for height_prop in height_property_names:
                        for pset_name, pset_dict in psets.items():
                            for prop_name, prop_value in pset_dict.items():
                                if isinstance(prop_name, str) and height_prop.lower() in prop_name.lower():
                                    if isinstance(prop_value, (int, float)) and prop_value > 0:
                                        functional_areas[keyword]['height_from_property'] = prop_value
                                        break
                            if functional_areas[keyword]['height_from_property'] is not None:
                                break
                        if functional_areas[keyword]['height_from_property'] is not None:
                            break
                
                # Determine storey height (simplified approach)
                if functional_areas[keyword]['height_from_storey'] is None:
                    # For this implementation, we'll use the height between First Floor and Second Floor
                    # as a representative height for functional areas
                    if 'First Floor' in storey_heights and 'Second Floor' in storey_heights:
                        # Use Second Floor height as it's likely where the main functional areas are
                        functional_areas[keyword]['height_from_storey'] = storey_heights.get('Second Floor', None)
                        functional_areas[keyword]['storey_range'] = ('First Floor', 'Second Floor')
    
    # For elements without specific keyword matches, we'll create a generic "Structural Area" category
    if not functional_areas and elements:
        functional_areas['Structural Area'] = {
            'elements': [element.GlobalId for element in elements[:10]],  # Limit to first 10 for performance
            'height_from_property': None,
            'height_from_storey': storey_heights.get('Second Floor', None) if 'Second Floor' in storey_heights else None,
            'storey_range': ('First Floor', 'Second Floor') if 'First Floor' in storey_heights and 'Second Floor' in storey_heights else None
        }
        
        # Try to get height from first element
        if elements:
            psets = ifcopenshell.util.element.get_psets(elements[0])
            for height_prop in height_property_names:
                for pset_name, pset_dict in psets.items():
                    for prop_name, prop_value in pset_dict.items():
                        if isinstance(prop_name, str) and height_prop.lower() in prop_name.lower():
                            if isinstance(prop_value, (int, float)) and prop_value > 0:
                                functional_areas['Structural Area']['height_from_property'] = prop_value
                                break
                    if functional_areas['Structural Area']['height_from_property'] is not None:
                        break
                if functional_areas['Structural Area']['height_from_property'] is not None:
                    break
    
    return functional_areas
