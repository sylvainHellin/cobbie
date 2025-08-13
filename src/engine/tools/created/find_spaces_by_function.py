import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional

def find_spaces_by_function(
    ifc_file: ifcopenshell.file,
    classification_types: Optional[List[str]] = None,
    category_descriptions: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    property_set_filters: Optional[Dict[str, List[str]]] = None,
    exact_match: bool = False,
    exclude_keywords: Optional[List[str]] = None
) -> List[Dict]:
    """
    Find spaces based on their functional classification or intended use.
    
    This function identifies spaces by examining their property sets for functional 
    classifications, category descriptions, and other semantic indicators. It can 
    search by classification codes, category descriptions, keywords, or specific 
    property set values.
    
    The function looks for classifications in standard property sets:
    - PSet_Revit_Identity Data: OmniClass Table 13 Category
    - PSet_Revit_Other: Category Description, Category Code
    
    Note: This implementation is optimized for IFC models exported from Revit,
    which use specific property set naming conventions.
    
    Args:
        ifc_file: The IFC file object to search
        classification_types: List of classification codes to search for 
                             (e.g., ["13-75 11 11: Storage Room", "13-75 41 14: Soiled Storage Room Space"])
        category_descriptions: List of category descriptions to search for
                              (e.g., ["Storage Room", "Soiled Storage Room Space"])
        keywords: List of keywords to search for in space names and property values
        property_set_filters: Dictionary mapping property set names to lists of property names to check
                             (e.g., {"PSet_Revit_Other": ["Category Description", "Category Code"]})
        exact_match: If True, performs exact matching instead of substring matching
        exclude_keywords: List of keywords to exclude from results (e.g., ["TECH", "DENTAL", "PHARM"])
    
    Returns:
        List of dictionaries containing matching spaces and their classification information.
        Each dictionary contains:
        - space: The IfcSpace entity instance
        - name: The space name
        - matching_criteria: List of criteria that matched
        - classification_info: Dictionary of relevant property set information
    """
    # Get all spaces
    spaces = ifc_file.by_type("IfcSpace")
    
    # Normalize search criteria to lowercase for case-insensitive matching
    classification_types_lower = [ct.lower() for ct in classification_types] if classification_types else []
    category_descriptions_lower = [cd.lower() for cd in category_descriptions] if category_descriptions else []
    keywords_lower = [kw.lower() for kw in keywords] if keywords else []
    exclude_keywords_lower = [ek.lower() for ek in exclude_keywords] if exclude_keywords else []
    
    matching_spaces = []
    
    # Determine which property sets and properties to check
    if property_set_filters is None:
        # Use default property sets when no filters specified
        property_sets_to_check = {
            "PSet_Revit_Identity Data": ["OmniClass Table 13 Category", "Name"],
            "PSet_Revit_Other": ["Category Description", "Category Code"]
        }
        use_default_search = True
    else:
        # Use only the specified property sets and properties
        property_sets_to_check = property_set_filters
        use_default_search = False
    
    # Check each space
    for space in spaces:
        space_name = space.Name if hasattr(space, 'Name') and space.Name else 'Unnamed'
        matching_criteria = []
        classification_info = {}
        
        # Check if space should be excluded based on name
        if exclude_keywords_lower:
            name_lower = space_name.lower()
            if any(exclude_keyword in name_lower for exclude_keyword in exclude_keywords_lower):
                continue  # Skip this space
        
        # Get property sets for this space
        psets = ifcopenshell.util.element.get_psets(space)
        
        # Check specified property sets and properties
        exclude_space = False
        
        # For default search, prioritize property set matching over name matching
        property_match_found = False
        
        for pset_name, property_names in property_sets_to_check.items():
            if pset_name in psets:
                pset_data = psets[pset_name]
                # Initialize classification info for this property set if not already done
                if pset_name not in classification_info:
                    classification_info[pset_name] = {}
                
                for prop_name in property_names:
                    if prop_name in pset_data and prop_name != 'id':
                        prop_value = pset_data[prop_name]
                        prop_value_str = str(prop_value)
                        classification_info[pset_name][prop_name] = prop_value
                        
                        # If property_set_filters is specified, we're looking for matches in those specific properties
                        if not use_default_search:
                            matching_criteria.append(f"{pset_name}.{prop_name} = '{prop_value_str}'")
                        
                        # Check for matching classification types (only for default search)
                        if classification_types_lower and use_default_search:
                            prop_value_lower = prop_value_str.lower()
                            for classification in classification_types_lower:
                                match_found = False
                                if exact_match:
                                    if classification == prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{classification}'")
                                        match_found = True
                                        property_match_found = True
                                else:
                                    if classification in prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{classification}'")
                                        match_found = True
                                        property_match_found = True
                                
                                # If a match was found, check if it contains exclude keywords
                                if match_found:
                                    if any(exclude_keyword in prop_value_lower for exclude_keyword in exclude_keywords_lower):
                                        exclude_space = True
                                        matching_criteria = []  # Clear matching criteria
                                        property_match_found = False
                                        break
                        
                        # Check for matching category descriptions (only for default search)
                        if category_descriptions_lower and use_default_search:
                            prop_value_lower = prop_value_str.lower()
                            for category in category_descriptions_lower:
                                match_found = False
                                if exact_match:
                                    if category == prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{category}'")
                                        match_found = True
                                        property_match_found = True
                                else:
                                    if category in prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{category}'")
                                        match_found = True
                                        property_match_found = True
                                
                                # If a match was found, check if it contains exclude keywords
                                if match_found:
                                    if any(exclude_keyword in prop_value_lower for exclude_keyword in exclude_keywords_lower):
                                        exclude_space = True
                                        matching_criteria = []  # Clear matching criteria
                                        property_match_found = False
                                        break
                        
                        # Check for keywords in property values (only for default search)
                        if keywords_lower and use_default_search:
                            prop_value_lower = prop_value_str.lower()
                            for keyword in keywords_lower:
                                match_found = False
                                if exact_match:
                                    if keyword == prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{keyword}'")
                                        match_found = True
                                        property_match_found = True
                                else:
                                    if keyword in prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{keyword}'")
                                        match_found = True
                                        property_match_found = True
                                
                                # If a match was found, check if it contains exclude keywords
                                if match_found:
                                    if any(exclude_keyword in prop_value_lower for exclude_keyword in exclude_keywords_lower):
                                        exclude_space = True
                                        matching_criteria = []  # Clear matching criteria
                                        property_match_found = False
                                        break
                        
                        # Check if property value contains exclude keywords (only for default search)
                        if exclude_keywords_lower and use_default_search:
                            prop_value_lower = prop_value_str.lower()
                            if any(exclude_keyword in prop_value_lower for exclude_keyword in exclude_keywords_lower):
                                exclude_space = True
                                matching_criteria = []  # Clear matching criteria
                                property_match_found = False
                                break  # Break inner loop to check next property
                
                # If space is marked for exclusion, break out of property set loop
                if exclude_space:
                    break
        
        # For default search, only check name keywords if no property matches were found
        if keywords_lower and use_default_search and not property_match_found:
            name_lower = space_name.lower()
            for keyword in keywords_lower:
                if exact_match:
                    if keyword == name_lower:
                        matching_criteria.append(f"Name exactly matches '{keyword}'")
                else:
                    if keyword in name_lower:
                        matching_criteria.append(f"Name contains '{keyword}'")
        
        # Check if space name contains exclude keywords (if no property matches were found)
        if exclude_keywords_lower and use_default_search and not property_match_found:
            name_lower = space_name.lower()
            if any(exclude_keyword in name_lower for exclude_keyword in exclude_keywords_lower):
                exclude_space = True
                matching_criteria = []  # Clear matching criteria
        
        # Determine if this space should be included in results
        should_include = False
        
        # If property_set_filters was specified, include spaces that have those properties
        if not use_default_search:
            should_include = len(matching_criteria) > 0 and not exclude_space
        else:
            # For default search, include if any matching criteria were found and not excluded
            # But prioritize property matches over name matches
            should_include = (len(matching_criteria) > 0 and not exclude_space and 
                            (property_match_found or (keywords_lower and not property_match_found)))
        
        # If criteria matched and space is not excluded, add to results
        if should_include:
            matching_spaces.append({
                'space': space,
                'name': space_name,
                'matching_criteria': matching_criteria,
                'classification_info': classification_info
            })
    
    # Remove duplicates based on space entity
    unique_spaces = []
    seen_spaces = set()
    for space_dict in matching_spaces:
        space_id = space_dict['space'].id()
        if space_id not in seen_spaces:
            seen_spaces.add(space_id)
            unique_spaces.append(space_dict)
    
    return unique_spaces