import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional, Union

def find_spaces_by_function(
    ifc_file: Union[ifcopenshell.file, str],
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
        ifc_file: The IFC file object to search or path to the IFC file
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
        - area: Area of the space in square feet (if available)
    """
    # Handle both string path and ifcopenshell.file object
    if isinstance(ifc_file, str):
        ifc_file = ifcopenshell.open(ifc_file)
    
    # Get all spaces
    spaces = ifc_file.by_type("IfcSpace")
    
    # Only use default values if no specific search criteria are provided
    use_defaults = not any([classification_types, category_descriptions, keywords])
    
    if use_defaults and category_descriptions is None:
        category_descriptions = [
            "Storage Room",
            "Soiled Storage Room Space",
            "Hazardous Material Storage Space",
            "Utility Storage Area",
            "Janitorial Storage Room",
            "Equipment Room",
            "Supply Room",
            "Linen Storage",
            "Cleaning Supply Storage"
        ]
    
    if use_defaults and keywords is None:
        keywords = [
            "storage",
            "soiled",
            "hazardous",
            "equipment",
            "janitor",
            "supply",
            "linen",
            "cleaning",
            "trash",
            "utility"
        ]
    
    # Normalize search criteria for case-insensitive matching
    classification_types_normalized = [ct.lower() for ct in classification_types] if classification_types else []
    category_descriptions_normalized = [cd.lower() for cd in category_descriptions] if category_descriptions else []
    keywords_normalized = [kw.lower() for kw in keywords] if keywords else []
    exclude_keywords_normalized = [ek.lower() for ek in exclude_keywords] if exclude_keywords else []
    
    matching_spaces = []
    
    # Determine which property sets and properties to check
    if property_set_filters is None:
        # Use default property sets when no filters specified
        property_sets_to_check = {
            "PSet_Revit_Identity Data": ["OmniClass Table 13 Category"],
            "PSet_Revit_Other": ["Category Description", "Category Code"]
        }
    else:
        # Use only the specified property sets and properties
        property_sets_to_check = property_set_filters
    
    # Check each space
    for space in spaces:
        space_name = getattr(space, 'Name', 'Unnamed') or 'Unnamed'
        matching_criteria = []
        classification_info = {}
        
        # Check if space should be excluded based on name
        if exclude_keywords_normalized:
            name_normalized = space_name.lower()
            if any(exclude_keyword in name_normalized for exclude_keyword in exclude_keywords_normalized):
                continue  # Skip this space
        
        # Get property sets for this space
        try:
            psets = ifcopenshell.util.element.get_psets(space)
        except Exception:
            # If we can't get property sets, continue with empty dict
            psets = {}
        
        # Track whether each search criterion is satisfied
        classification_match = not classification_types  # True if no classification search
        category_match = not category_descriptions  # True if no category search
        keyword_match = not keywords  # True if no keyword search
        
        # Check specified property sets and properties
        for pset_name, property_names in property_sets_to_check.items():
            if pset_name in psets:
                pset_data = psets[pset_name]
                # Initialize classification info for this property set if not already done
                if pset_name not in classification_info:
                    classification_info[pset_name] = {}
                
                for prop_name in property_names:
                    if prop_name in pset_data:
                        prop_value = pset_data[prop_name]
                        prop_value_str = str(prop_value).strip()
                        classification_info[pset_name][prop_name] = prop_value
                        
                        # Check for matching classification types
                        if classification_types_normalized:
                            prop_value_normalized = prop_value_str.lower()
                            for classification in classification_types_normalized:
                                if exact_match:
                                    # For exact matching, check if the classification matches exactly
                                    if classification == prop_value_normalized:
                                        classification_match = True
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{classification}'")
                                else:
                                    # For substring matching, check if classification is contained
                                    if classification in prop_value_normalized:
                                        classification_match = True
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{classification}'")
                        
                        # Check for matching category descriptions
                        if category_descriptions_normalized:
                            prop_value_normalized = prop_value_str.lower()
                            for category in category_descriptions_normalized:
                                if exact_match:
                                    # For exact matching, check if the category matches exactly
                                    if category == prop_value_normalized:
                                        category_match = True
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{category}'")
                                else:
                                    # For substring matching, check if category is contained
                                    if category in prop_value_normalized:
                                        category_match = True
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{category}'")
                        
                        # Check for keywords in property values
                        if keywords_normalized:
                            prop_value_normalized = prop_value_str.lower()
                            for keyword in keywords_normalized:
                                if exact_match:
                                    # For exact matching, check if the keyword matches exactly
                                    if keyword == prop_value_normalized:
                                        keyword_match = True
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{keyword}'")
                                else:
                                    # For substring matching, check if keyword is contained
                                    # Special handling for laboratory searches
                                    if keyword in ['lab', 'laboratory']:
                                        if 'lab' in prop_value_normalized or 'laboratory' in prop_value_normalized:
                                            keyword_match = True
                                            matching_criteria.append(f"{pset_name}.{prop_name} contains '{keyword}'")
                                    elif keyword in prop_value_normalized:
                                        keyword_match = True
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{keyword}'")
        
        # Check name keywords if needed
        if keywords_normalized and not keyword_match:
            name_normalized = space_name.lower()
            for keyword in keywords_normalized:
                if exact_match:
                    if keyword == name_normalized:
                        keyword_match = True
                        matching_criteria.append(f"Name exactly matches '{keyword}'")
                else:
                    # Special handling for laboratory searches
                    if keyword in ['lab', 'laboratory']:
                        if 'lab' in name_normalized or 'laboratory' in name_normalized:
                            keyword_match = True
                            matching_criteria.append(f"Name contains '{keyword}'")
                    elif keyword in name_normalized:
                        keyword_match = True
                        matching_criteria.append(f"Name contains '{keyword}'")
        
        # Only include space if ALL specified criteria are met
        if classification_match and category_match and keyword_match:
            # Extract area information if available
            area = None
            if psets:
                # Look for area in common property sets
                for pset_name in ['PSet_Revit_Dimensions', 'GSA Space Areas']:
                    if pset_name in psets:
                        pset_data = psets[pset_name]
                        # Look for area properties
                        for prop_name in ['Area', 'GSA BIM Area']:
                            if prop_name in pset_data:
                                area_value = pset_data[prop_name]
                                if isinstance(area_value, (int, float)):
                                    area = area_value
                                    break
                        if area is not None:
                            break
            
            matching_spaces.append({
                'space': space,
                'name': space_name,
                'matching_criteria': matching_criteria,
                'classification_info': classification_info,
                'area': area  # Include area information
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