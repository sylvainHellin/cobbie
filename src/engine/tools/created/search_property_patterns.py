import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional
import re

def search_property_patterns(
    model_path: str,
    search_patterns: List[str],
    element_types: Optional[List[str]] = None,
    search_scope: str = "all",
    case_sensitive: bool = False
) -> List[Dict[str, Any]]:
    """
    Search for specific property patterns across all elements in an IFC model.
    
    Args:
        model_path (str): Path to the IFC model file
        search_patterns (List[str]): List of keywords or patterns to search for
        element_types (List[str], optional): Specific element types to search within (default: None, meaning all types)
        search_scope (str, optional): Where to search - "element_names", "property_sets", "property_values", or "all" (default: "all")
        case_sensitive (bool, optional): Whether the search should be case sensitive (default: False)
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing detailed information about matching elements
        
    Note:
        This function works with IFC models that may contain properties from various BIM authoring software 
        such as Revit (PSet_Revit_*), ArchiCAD, or other IFC-compliant applications.
    """
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all elements or filter by type
    if element_types:
        elements = []
        for element_type in element_types:
            elements.extend(model.by_type(element_type))
    else:
        elements = model.by_type("IfcProduct")  # Get all IfcProduct elements
    
    # Prepare search patterns based on case sensitivity
    if not case_sensitive:
        search_patterns = [pattern.lower() for pattern in search_patterns]
    
    results = []
    
    # Process each element
    for element in elements:
        element_name = element.Name if hasattr(element, 'Name') and element.Name else ""
        
        # Check element name if in scope
        if search_scope in ["element_names", "all"]:
            # Check if any pattern matches the element name
            name_to_check = element_name.lower() if not case_sensitive else element_name
            for pattern in search_patterns:
                if pattern in name_to_check:
                    results.append({
                        "element_name": element_name,
                        "element_guid": element.GlobalId,
                        "element_type": element.is_a(),
                        "match_location": "element_name",
                        "match_detail": pattern,
                        "property_set": None,
                        "property_name": None,
                        "property_value": None
                    })
        
        # Check properties if in scope
        if search_scope in ["property_sets", "property_values", "all"]:
            # Get property sets for this element
            try:
                property_sets = ifcopenshell.util.element.get_psets(element)
            except Exception:
                # Skip elements that don't have property sets
                continue
                
            # Check each property set
            for pset_name, pset_data in property_sets.items():
                # Check property set name if in scope
                if search_scope in ["property_sets", "all"]:
                    pset_name_to_check = pset_name.lower() if not case_sensitive else pset_name
                    for pattern in search_patterns:
                        if pattern in pset_name_to_check:
                            results.append({
                                "element_name": element_name,
                                "element_guid": element.GlobalId,
                                "element_type": element.is_a(),
                                "match_location": "property_set_name",
                                "match_detail": pattern,
                                "property_set": pset_name,
                                "property_name": None,
                                "property_value": None
                            })
                
                # Check property names and values if in scope
                if search_scope in ["property_values", "all"]:
                    for prop_name, prop_value in pset_data.items():
                        # Skip the 'id' property which is not a real property
                        if prop_name == 'id':
                            continue
                            
                        # Check property name
                        prop_name_to_check = prop_name.lower() if not case_sensitive else prop_name
                        for pattern in search_patterns:
                            if pattern in prop_name_to_check:
                                results.append({
                                    "element_name": element_name,
                                    "element_guid": element.GlobalId,
                                    "element_type": element.is_a(),
                                    "match_location": "property_name",
                                    "match_detail": pattern,
                                    "property_set": pset_name,
                                    "property_name": prop_name,
                                    "property_value": prop_value
                                })
                        
                        # Check property value
                        prop_value_str = str(prop_value) if prop_value is not None else ""
                        prop_value_to_check = prop_value_str.lower() if not case_sensitive else prop_value_str
                        for pattern in search_patterns:
                            if pattern in prop_value_to_check:
                                results.append({
                                    "element_name": element_name,
                                    "element_guid": element.GlobalId,
                                    "element_type": element.is_a(),
                                    "match_location": "property_value",
                                    "match_detail": pattern,
                                    "property_set": pset_name,
                                    "property_name": prop_name,
                                    "property_value": prop_value
                                })
    
    return results