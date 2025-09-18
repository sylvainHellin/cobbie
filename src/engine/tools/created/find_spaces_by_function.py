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
    
    # Default search criteria for storage spaces if not provided
    if category_descriptions is None:
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
    
    if keywords is None:
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
        if exclude_keywords_lower:
            name_lower = space_name.lower()
            if any(exclude_keyword in name_lower for exclude_keyword in exclude_keywords_lower):
                continue  # Skip this space
        
        # Get property sets for this space
        try:
            psets = ifcopenshell.util.element.get_psets(space)
        except Exception:
            # If we can't get property sets, continue with empty dict
            psets = {}
        
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
                        prop_value_str = str(prop_value)
                        classification_info[pset_name][prop_name] = prop_value
                        
                        # Check for matching classification types
                        if classification_types_lower:
                            prop_value_lower = prop_value_str.lower()
                            for classification in classification_types_lower:
                                if exact_match:
                                    if classification == prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{classification}'")
                                else:
                                    if classification in prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{classification}'")
                        
                        # Check for matching category descriptions
                        if category_descriptions_lower:
                            prop_value_lower = prop_value_str.lower()
                            for category in category_descriptions_lower:
                                if exact_match:
                                    if category == prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{category}'")
                                else:
                                    if category in prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{category}'")
                        
                        # Check for keywords in property values
                        if keywords_lower:
                            prop_value_lower = prop_value_str.lower()
                            for keyword in keywords_lower:
                                if exact_match:
                                    if keyword == prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} exactly matches '{keyword}'")
                                else:
                                    if keyword in prop_value_lower:
                                        matching_criteria.append(f"{pset_name}.{prop_name} contains '{keyword}'")
        
        # Check name keywords if no property matches were found
        if keywords_lower and not matching_criteria:
            name_lower = space_name.lower()
            for keyword in keywords_lower:
                if exact_match:
                    if keyword == name_lower:
                        matching_criteria.append(f"Name exactly matches '{keyword}'")
                else:
                    if keyword in name_lower:
                        matching_criteria.append(f"Name contains '{keyword}'")
        
        # If criteria matched and space is not excluded, add to results
        if matching_criteria:
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