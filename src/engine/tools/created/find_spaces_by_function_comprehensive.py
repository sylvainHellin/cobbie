import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict

def find_spaces_by_function_comprehensive(model_path: str, function_keywords: List[str]) -> List[Dict]:
    """
    Find spaces by their functional classification using a comprehensive search approach.
    
    This function searches for spaces by checking multiple sources for functional classification:
    1. Space entity names
    2. Space entity LongName attribute  
    3. Property sets that may contain functional classification information:
       - Revit: PSet_Revit_Identity Data (OmniClass Table 13 Category), PSet_Revit_Other (Category Description)
       - ArchiCAD: Graphisoft AC110 SPACE and other property sets
       - Other BIM software: Any property sets containing relevant classification fields
    
    Args:
        model_path (str): Path to the IFC file
        function_keywords (List[str]): List of keywords to search for in space functional classifications
        
    Returns:
        List[Dict]: List of dictionaries containing comprehensive information about matching spaces
        
    Note:
        This function is designed to work with IFC models exported from various BIM software
        (Revit, ArchiCAD, etc.) by checking multiple property set patterns that commonly
        contain functional classification information.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all spaces
    spaces = model.by_type("IfcSpace")
    
    # List to store matching spaces
    matching_spaces = []
    
    # Convert keywords to lowercase for case-insensitive matching
    function_keywords_lower = [keyword.lower() for keyword in function_keywords]
    
    # Define common property names that might contain functional classification
    functional_property_names = [
        'OmniClass Table 13 Category',
        'Category Description', 
        'Function',
        'Usage',
        'SpaceType',
        'RoomType',
        'Classification',
        'Purpose',
        'Category',
        'Type',
        'Description'
    ]
    
    # Iterate through all spaces
    for space in spaces:
        is_match = False
        matching_sources = []  # To track which sources matched
        
        # Check space Name
        if space.Name:
            if any(keyword in space.Name.lower() for keyword in function_keywords_lower):
                is_match = True
                matching_sources.append("Name")
        
        # Check space LongName
        if space.LongName and not is_match:
            if any(keyword in space.LongName.lower() for keyword in function_keywords_lower):
                is_match = True
                matching_sources.append("LongName")
        
        # Check property sets for functional classification
        if not is_match:
            try:
                # Get all property sets for this space
                property_sets = ifcopenshell.util.element.get_psets(space)
                
                # Search through all property sets for functional classification
                for pset_name, pset_data in property_sets.items():
                    if not pset_name or not isinstance(pset_data, dict):
                        continue
                        
                    # Check Revit-specific property sets
                    if pset_name == "PSet_Revit_Identity Data":
                        if "OmniClass Table 13 Category" in pset_data:
                            prop_value = pset_data["OmniClass Table 13 Category"]
                            if isinstance(prop_value, str) and any(keyword in prop_value.lower() for keyword in function_keywords_lower):
                                is_match = True
                                matching_sources.append(f"{pset_name}: OmniClass Table 13 Category")
                                break
                    
                    elif pset_name == "PSet_Revit_Other":
                        if "Category Description" in pset_data:
                            prop_value = pset_data["Category Description"]
                            if isinstance(prop_value, str) and any(keyword in prop_value.lower() for keyword in function_keywords_lower):
                                is_match = True
                                matching_sources.append(f"{pset_name}: Category Description")
                                break
                    
                    # Check ArchiCAD and other property sets
                    else:
                        # Look for any property that might contain functional classification
                        for prop_name, prop_value in pset_data.items():
                            # Check if property name suggests functional classification
                            if any(func_prop.lower() in prop_name.lower() for func_prop in functional_property_names):
                                if isinstance(prop_value, str) and any(keyword in prop_value.lower() for keyword in function_keywords_lower):
                                    is_match = True
                                    matching_sources.append(f"{pset_name}: {prop_name}")
                                    break
                        
                        if is_match:
                            break
                            
            except Exception:
                # If there's an error accessing property sets, continue with other checks
                pass
        
        # If this space matches our criteria, add it to results
        if is_match:
            # Get area properties
            area = None
            gross_area = None
            net_area = None
            all_psets = {}
            
            try:
                property_sets = ifcopenshell.util.element.get_psets(space)
                # Look for area properties in various property sets
                for pset_name, pset_data in property_sets.items():
                    if pset_name and isinstance(pset_data, dict):
                        all_psets[pset_name] = pset_data
                        # Check for various area property names
                        for area_prop in ['Area', 'GrossArea', 'NetArea', 'Gross Floor Area', 'Net Floor Area']:
                            if area_prop in pset_data:
                                if area_prop == 'Area':
                                    area = pset_data[area_prop]
                                elif 'Gross' in area_prop:
                                    gross_area = pset_data[area_prop]
                                elif 'Net' in area_prop:
                                    net_area = pset_data[area_prop]
            except Exception:
                pass
            
            # Create result dictionary with comprehensive information
            space_info = {
                "GlobalId": space.GlobalId,
                "Name": space.Name,
                "LongName": space.LongName,
                "Description": getattr(space, "Description", None),
                "ObjectType": getattr(space, "ObjectType", None),
                "Area": area,
                "GrossArea": gross_area,
                "NetArea": net_area,
                "Properties": all_psets,
                "MatchingSources": matching_sources
            }
            
            matching_spaces.append(space_info)
    
    return matching_spaces