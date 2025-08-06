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

def get_space_areas_by_function(ifc_file_path: str, function_keywords: List[str]) -> Dict[str, Any]:
    """
    Extract area properties from IfcSpace elements based on functional keywords.
    
    This function searches for IfcSpace elements in an IFC model that match the provided
    functional keywords and extracts their area properties. It handles various property
    set conventions including PSet_Revit_Dimensions.Area and GSA Space Areas.GSA BIM Area.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        function_keywords (List[str]): List of keywords to match against space functions
        
    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'spaces': List of dictionaries with space information (name, area, function)
            - 'total_area': Total area of all matching spaces
            - 'count': Number of matching spaces
            
    Note:
        This function assumes the IFC model follows common property set conventions:
        - PSet_Revit_Dimensions.Area (for Revit-exported IFCs)
        - GSA Space Areas.GSA BIM Area (for GSA-compliant models)
        - Pset_SpaceCommon.Area (for standard IFC property sets)
    """
    
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Get all IfcSpace elements
    spaces = ifc_file.by_type("IfcSpace")
    
    matching_spaces = []
    total_area = 0.0
    
    # Convert keywords to lowercase for case-insensitive matching
    keywords_lower = [keyword.lower() for keyword in function_keywords]
    
    for space in spaces:
        # Get space name and description
        space_name = getattr(space, 'Name', '') or ''
        space_description = getattr(space, 'Description', '') or ''
        space_long_name = getattr(space, 'LongName', '') or ''
        
        # Get all property sets for this space
        psets = ifcopenshell.util.element.get_psets(space)
        
        # Check if space matches any of the functional keywords
        is_match = False
        space_function = ""
        
        # Check in space name, description, and long name
        check_fields = [space_name, space_description, space_long_name]
        
        # Also check in property set values
        for pset_name, pset_dict in psets.items():
            for prop_name, prop_value in pset_dict.items():
                if prop_name != 'id':  # Skip the 'id' field
                    check_fields.append(str(prop_value))
                    # If this is a function-related property, store it
                    if 'function' in prop_name.lower() or 'category' in prop_name.lower():
                        space_function = str(prop_value)
        
        # Check if any keyword matches any field
        for field in check_fields:
            field_lower = field.lower()
            for keyword in keywords_lower:
                if keyword in field_lower:
                    is_match = True
                    if not space_function:
                        space_function = field
                    break
            if is_match:
                break
        
        # If space matches, extract area information
        if is_match:
            area = 0.0
            
            # Look for area in various property sets
            # Common Revit property set
            if 'PSet_Revit_Dimensions' in psets and 'Area' in psets['PSet_Revit_Dimensions']:
                area = float(psets['PSet_Revit_Dimensions']['Area'])
            # GSA property set
            elif 'GSA Space Areas' in psets and 'GSA BIM Area' in psets['GSA Space Areas']:
                area = float(psets['GSA Space Areas']['GSA BIM Area'])
            # Standard IFC property set
            elif 'Pset_SpaceCommon' in psets and 'Area' in psets['Pset_SpaceCommon']:
                area = float(psets['Pset_SpaceCommon']['Area'])
            # Check for any property set containing 'Area'
            else:
                for pset_name, pset_dict in psets.items():
                    for prop_name, prop_value in pset_dict.items():
                        if 'area' in prop_name.lower() and prop_name != 'id':
                            try:
                                area = float(prop_value)
                                break
                            except (ValueError, TypeError):
                                continue
                    if area > 0:
                        break
            
            space_info = {
                'name': space_name,
                'area': area,
                'function': space_function
            }
            
            matching_spaces.append(space_info)
            total_area += area
    
    return {
        'spaces': matching_spaces,
        'total_area': total_area,
        'count': len(matching_spaces)
    }