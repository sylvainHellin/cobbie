import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def get_structural_load_capacity(
    model_path: str,
    element_type: Optional[str] = None,
    element_name_pattern: Optional[str] = None,
    load_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves structural load capacity information from IFC elements.
    
    This function searches for load capacity information (live load, dead load, total load capacity)
    in structural elements. It focuses on common structural element types and checks standard property
    sets where load information is typically stored.
    
    Note: Load capacity information requires explicit setup in the BIM authoring tool (e.g., Revit).
    If not explicitly defined, this information may not be available in the IFC model.
    
    Args:
        model_path (str): Path to the IFC model file
        element_type (str, optional): Specific structural element type to analyze 
            (IfcSlab, IfcBeam, IfcColumn, IfcWall, IfcWallStandardCase). 
            If None, check all structural elements.
        element_name_pattern (str, optional): Pattern to filter elements by name 
            (case-insensitive substring match)
        load_type (str, optional): Specific type of load to search for 
            ("live", "dead", "total", "capacity"). If None, search for all load types.
            
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing load capacity information:
            - element_name: Name of the structural element
            - element_guid: GlobalId of the element
            - element_type: IFC type of the element
            - load_type: Type of load (live, dead, total, capacity)
            - load_value: Load value with units if available
            - property_set: Name of the property set where the load information was found
            - property_name: Exact property name where the load information was found
            - units: Units of the load value if specified
            - notes: Additional information about the load capacity
    """
    
    # Define structural element types to search for
    structural_element_types = [
        "IfcSlab", 
        "IfcBeam", 
        "IfcColumn", 
        "IfcWall", 
        "IfcWallStandardCase"
    ]
    
    # If element_type is specified, use only that type
    if element_type:
        if element_type in structural_element_types:
            element_types_to_check = [element_type]
        else:
            raise ValueError(f"Invalid element_type: {element_type}. Must be one of {structural_element_types}")
    else:
        element_types_to_check = structural_element_types
    
    # Load the IFC model
    try:
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise FileNotFoundError(f"Could not open IFC model at {model_path}: {str(e)}")
    
    # Get all structural elements
    structural_elements = []
    for elem_type in element_types_to_check:
        elements = model.by_type(elem_type)
        structural_elements.extend(elements)
    
    # Filter by element name pattern if specified
    if element_name_pattern:
        filtered_elements = []
        for element in structural_elements:
            element_name = getattr(element, 'Name', '') or ''
            if element_name_pattern.lower() in element_name.lower():
                filtered_elements.append(element)
        structural_elements = filtered_elements
    
    # Define load-related keywords to search for
    load_keywords = {
        "live": ["live", "live_load", "liveload", "occupancy"],
        "dead": ["dead", "dead_load", "deadload", "self_weight"],
        "total": ["total", "total_load", "combined"],
        "capacity": ["capacity", "load_capacity", "bearing_capacity", "strength"]
    }
    
    # If load_type is specified, use only those keywords
    if load_type:
        if load_type in load_keywords:
            keywords_to_search = {load_type: load_keywords[load_type]}
        else:
            raise ValueError(f"Invalid load_type: {load_type}. Must be one of {list(load_keywords.keys())}")
    else:
        keywords_to_search = load_keywords
    
    # List to store found load information
    load_info_list = []
    
    # Property sets to check for load information
    property_sets_to_check = [
        "PSet_Revit_Structural",
        "PSet_Revit_Structural Analysis",
        "Pset_SlabCommon",
        "Pset_WallCommon",
        "Pset_ColumnCommon",
        "Pset_BeamCommon",
        "PSet_Revit_Analytical Model",
        "Structural",
        "Analysis",
        "Load"
    ]
    
    # Iterate through all structural elements
    for element in structural_elements:
        element_name = getattr(element, 'Name', '') or 'Unnamed Element'
        element_guid = element.GlobalId
        element_type_name = element.is_a()
        
        # Get all property sets for this element
        try:
            psets = ifcopenshell.util.element.get_psets(element)
        except Exception:
            # If we can't get property sets, continue to next element
            continue
        
        # Check each property set for load-related properties
        for pset_name, pset_data in psets.items():
            # Check if this property set is one we should examine
            if any(keyword.lower() in pset_name.lower() for keyword in property_sets_to_check):
                # Check each property in the property set
                for prop_name, prop_value in pset_data.items():
                    # Check if property name matches any of our load keywords
                    for search_load_type, keywords in keywords_to_search.items():
                        if any(keyword in prop_name.lower() for keyword in keywords):
                            # Found a load-related property
                            load_info = {
                                "element_name": element_name,
                                "element_guid": element_guid,
                                "element_type": element_type_name,
                                "load_type": search_load_type,
                                "load_value": prop_value,
                                "property_set": pset_name,
                                "property_name": prop_name,
                                "units": "unknown",  # Units would need to be extracted separately
                                "notes": "Load information found in property set"
                            }
                            load_info_list.append(load_info)
    
    # If no load information was found, provide a helpful message
    if not load_info_list:
        # Check if we found any structural elements at all
        if structural_elements:
            no_data_info = {
                "element_name": "N/A",
                "element_guid": "N/A",
                "element_type": "N/A",
                "load_type": "N/A",
                "load_value": "N/A",
                "property_set": "N/A",
                "property_name": "N/A",
                "units": "N/A",
                "notes": f"No load capacity information found in {len(structural_elements)} structural elements. "
                         "Load capacity information must be explicitly defined in the BIM authoring tool "
                         "(e.g., Revit) and may not be available in all IFC exports."
            }
            load_info_list.append(no_data_info)
        else:
            no_elements_info = {
                "element_name": "N/A",
                "element_guid": "N/A",
                "element_type": "N/A",
                "load_type": "N/A",
                "load_value": "N/A",
                "property_set": "N/A",
                "property_name": "N/A",
                "units": "N/A",
                "notes": "No structural elements found in the model."
            }
            load_info_list.append(no_elements_info)
    
    return load_info_list