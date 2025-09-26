import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict

def find_spaces_by_function_comprehensive(model_path: str, function_keywords: List[str]) -> List[Dict]:
    """
    Find spaces by their functional classification using a comprehensive search approach.
    
    This function searches for spaces by checking specific property sets that contain
    functional classification information:
    1. Space entity names
    2. Space entity LongName attribute
    3. PSet_Revit_Identity Data -> OmniClass Table 13 Category
    4. PSet_Revit_Other -> Category Description
    
    Args:
        model_path (str): Path to the IFC file
        function_keywords (List[str]): List of keywords to search for in space functional classifications
        
    Returns:
        List[Dict]: List of dictionaries containing comprehensive information about matching spaces
        
    Note:
        This function is designed to work with IFC models exported from Revit, 
        which store functional classification in specific property sets.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all spaces
    spaces = model.by_type("IfcSpace")
    
    # List to store matching spaces
    matching_spaces = []
    
    # Convert keywords to lowercase for case-insensitive matching
    function_keywords_lower = [keyword.lower() for keyword in function_keywords]
    
    # Iterate through all spaces
    for space in spaces:
        is_match = False
        matching_pset_info = {}  # To store information about which property sets matched
        
        # Check space Name
        if space.Name:
            if any(keyword in space.Name.lower() for keyword in function_keywords_lower):
                is_match = True
        
        # Check space LongName
        if space.LongName and not is_match:
            if any(keyword in space.LongName.lower() for keyword in function_keywords_lower):
                is_match = True
        
        # Check specific property sets for functional classification if not already matched
        if not is_match:
            try:
                # Get all property sets for this space
                property_sets = ifcopenshell.util.element.get_psets(space)
                
                # Check PSet_Revit_Identity Data for OmniClass Table 13 Category
                if "PSet_Revit_Identity Data" in property_sets:
                    pset_data = property_sets["PSet_Revit_Identity Data"]
                    if "OmniClass Table 13 Category" in pset_data:
                        prop_value = pset_data["OmniClass Table 13 Category"]
                        if isinstance(prop_value, str) and any(keyword in prop_value.lower() for keyword in function_keywords_lower):
                            is_match = True
                            matching_pset_info["PSet_Revit_Identity Data"] = {
                                "OmniClass Table 13 Category": prop_value
                            }
                
                # Check PSet_Revit_Other for Category Description
                if not is_match and "PSet_Revit_Other" in property_sets:
                    pset_data = property_sets["PSet_Revit_Other"]
                    if "Category Description" in pset_data:
                        prop_value = pset_data["Category Description"]
                        if isinstance(prop_value, str) and any(keyword in prop_value.lower() for keyword in function_keywords_lower):
                            is_match = True
                            matching_pset_info["PSet_Revit_Other"] = {
                                "Category Description": prop_value
                            }
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
                    all_psets[pset_name] = pset_data
                    if 'Area' in pset_data:
                        area = pset_data['Area']
                    if 'GrossArea' in pset_data:
                        gross_area = pset_data['GrossArea']
                    if 'NetArea' in pset_data:
                        net_area = pset_data['NetArea']
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
                "Properties": all_psets
            }
            
            matching_spaces.append(space_info)
    
    return matching_spaces