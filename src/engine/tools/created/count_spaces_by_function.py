
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

def count_spaces_by_function(ifc_file_path: str, function_keywords: List[str], case_sensitive: bool = False) -> int:
    """
    Count the number of spaces/rooms in an IFC model that match specific functional keywords.
    
    This function searches for matches in:
    1. Space Name attribute
    2. Space LongName attribute
    3. Space Description attribute
    4. All property set names, property names, and property values
    
    For IFC models exported from Revit, this includes checking:
    - PSet_Revit_Identity Data.Name
    - PSet_Revit_Identity Data.OmniClass Table 13 Category
    
    Args:
        ifc_file_path (str): Path to the IFC file
        function_keywords (List[str]): List of keywords to match against space names, descriptions, and properties
        case_sensitive (bool): Whether to perform case-sensitive matching (default: False)
        
    Returns:
        int: Number of spaces matching any of the keywords
        
    Example:
        >>> # Count bedrooms
        >>> bedroom_count = count_spaces_by_function("model.ifc", ["bedroom", "bed room", "master bedroom"])
        >>> # Count bathrooms (case sensitive)
        >>> bathroom_count = count_spaces_by_function("model.ifc", ["BATH", "SHOWER"], case_sensitive=True)
    """
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
        
        # Find all IfcSpace elements
        spaces = ifc_file.by_type("IfcSpace")
        
        # If no spaces found, return 0
        if not spaces:
            return 0
            
        # Process keywords based on case sensitivity
        if case_sensitive:
            processed_keywords = function_keywords
        else:
            processed_keywords = [kw.lower() for kw in function_keywords]
            
        matching_spaces_count = 0
        
        # Check each space
        for space in spaces:
            is_match = False
            
            # Check space attributes: Name, Description, LongName
            space_attributes = [
                getattr(space, 'Name', '') or '',
                getattr(space, 'Description', '') or '',
                getattr(space, 'LongName', '') or ''
            ]
            
            # Process attributes based on case sensitivity
            if case_sensitive:
                processed_attributes = space_attributes
            else:
                processed_attributes = [attr.lower() for attr in space_attributes]
                
            # Combine all text to search
            combined_text = ' '.join(processed_attributes).strip()
            
            # Check for keyword matches in combined text
            for keyword in processed_keywords:
                if keyword in combined_text:
                    is_match = True
                    break
                    
            # If not matched yet, check property sets
            if not is_match:
                try:
                    # Get all property sets for the space
                    psets = ifcopenshell.util.element.get_psets(space)
                    
                    # Check each property set
                    for pset_name, properties in psets.items():
                        # Check property set name
                        check_pset_name = pset_name.lower() if not case_sensitive else pset_name
                        for keyword in processed_keywords:
                            if keyword in check_pset_name:
                                is_match = True
                                break
                                
                        if is_match:
                            break
                            
                        # Check property names and values
                        for prop_name, prop_value in properties.items():
                            # Check property name
                            check_prop_name = prop_name.lower() if not case_sensitive else prop_name
                            for keyword in processed_keywords:
                                if keyword in check_prop_name:
                                    is_match = True
                                    break
                                    
                            if is_match:
                                break
                                
                            # Check property value (convert to string first)
                            prop_value_str = str(prop_value).lower() if not case_sensitive else str(prop_value)
                            for keyword in processed_keywords:
                                if keyword in prop_value_str:
                                    is_match = True
                                    break
                                    
                            if is_match:
                                break
                                
                        if is_match:
                            break
                except Exception as e:
                    # If there's an error getting properties, continue with other checks
                    pass
                    
            if is_match:
                matching_spaces_count += 1
                
        return matching_spaces_count
        
    except FileNotFoundError:
        return 0
    except Exception as e:
        # For any other exception, return 0
        # In a production environment, you might want to log this or handle it differently
        return 0
