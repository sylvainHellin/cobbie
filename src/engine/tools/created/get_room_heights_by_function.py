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

def get_room_heights_by_function(ifc_file_path: str, function_keywords: List[str], height_property_names: List[str]) -> Dict[str, Union[float, List[float]]]:
    """
    Identifies rooms/spaces by functional role and extracts their height properties from an IFC model.
    
    This function searches for elements in an IFC model that match functional keywords and extracts
    height information from those elements. It's designed to work with models that may not have
    explicit IfcSpace elements, which is common in some IFC exports.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        function_keywords (List[str]): List of keywords to match for identifying functional rooms
            (e.g., ['reception', 'waiting', 'consultation', 'interaction'])
        height_property_names (List[str]): List of property names to check for height values
            (e.g., ['Height', 'Elevation at Bottom', 'Elevation at Top'])
            
    Returns:
        Dict[str, Union[float, List[float]]]: A dictionary where keys are the function keywords
            and values are either a single height (float) or list of heights (List[float]) for
            elements matching that function. If no elements are found for a keyword, the key
            will not be present in the dictionary.
            
    Note:
        This function is designed for IFC models exported from Revit or similar BIM software.
        It looks for elements with properties that indicate room functions and height information.
        In models without explicit IfcSpace elements, it searches building elements for functional
        indicators.
    """
    import ifcopenshell
    import ifcopenshell.util.element
    
    # Load the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Initialize result dictionary
    result = {}
    
    # Get building elements (more likely to represent rooms)
    building_elements = model.by_type("IfcBuildingElement")
    
    # Limit the number of elements to process to avoid performance issues
    max_elements = 500
    search_elements = building_elements[:max_elements] if len(building_elements) > max_elements else building_elements
    
    # For each function keyword, find matching elements and their heights
    for keyword in function_keywords:
        matching_elements = []
        
        # Search for elements with names or properties matching the keyword
        for element in search_elements:
            # Check element name
            if hasattr(element, 'Name') and element.Name:
                if keyword.lower() in element.Name.lower():
                    matching_elements.append(element)
                    continue
            
            # Check element properties (limited to avoid performance issues)
            try:
                properties = ifcopenshell.util.element.get_psets(element)
                prop_count = 0
                for pset_name, pset_dict in properties.items():
                    if prop_count > 50:  # Limit property checks
                        break
                    for prop_name, prop_value in pset_dict.items():
                        prop_count += 1
                        if prop_count > 50:  # Limit property checks
                            break
                        # Check property name or value
                        if keyword.lower() in str(prop_name).lower() or keyword.lower() in str(prop_value).lower():
                            matching_elements.append(element)
                            break
                    if element in matching_elements:
                        break
            except:
                # Skip elements that cause errors when getting properties
                continue
        
        # For each matching element, try to extract height information
        heights = []
        for element in matching_elements:
            element_heights = []
            
            # Get element properties
            try:
                properties = ifcopenshell.util.element.get_psets(element)
                prop_count = 0
                for pset_name, pset_dict in properties.items():
                    if prop_count > 30:  # Limit property checks
                        break
                    for prop_name, prop_value in pset_dict.items():
                        prop_count += 1
                        if prop_count > 30:  # Limit property checks
                            break
                        # Check if this property name matches any of our height property names
                        for height_prop in height_property_names:
                            if height_prop.lower() in str(prop_name).lower():
                                # Try to convert the property value to a float
                                try:
                                    # Handle different types of property values
                                    if isinstance(prop_value, (int, float)):
                                        element_heights.append(float(prop_value))
                                    elif isinstance(prop_value, str):
                                        # Try to extract numeric value from string
                                        import re
                                        numbers = re.findall(r'-?\d+\.?\d*', prop_value)
                                        if numbers:
                                            element_heights.append(float(numbers[0]))
                                except (ValueError, TypeError):
                                    # Skip values that can't be converted to float
                                    pass
            
                # If we found height properties, add them to our results
                if element_heights:
                    heights.extend(element_heights)
            except:
                # Skip elements that cause errors when getting properties
                continue
        
        # Add to result dictionary
        if heights:
            # If only one height, store as scalar, otherwise store as list
            result[keyword] = heights[0] if len(heights) == 1 else heights
    
    return result
