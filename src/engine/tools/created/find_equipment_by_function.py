
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


def find_equipment_by_function(ifc_file_path: str, equipment_function: str, equipment_keywords: List[str] = None, element_types: List[str] = None) -> List[Dict[str, Any]]:
    """
    Searches for equipment elements in an IFC model based on their functional role or type.
    
    This function is designed to work with equipment from various BIM authoring software,
    particularly Revit-exported IFC models which use PSet_Revit_* property sets.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        equipment_function (str): The functional role of the equipment (e.g., "fire extinguisher", "fire alarm")
        equipment_keywords (List[str], optional): Custom keywords to search for. Defaults to None.
        element_types (List[str], optional): Custom element types to search. Defaults to None.
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing information about found equipment elements.
                             Each dictionary contains:
                             - name: Element name
                             - type: IFC entity type
                             - global_id: Element GlobalId
                             - location: Spatial container name
                             - location_type: Spatial container type
    """
    # Define default element types if not provided
    if element_types is None:
        element_types = [
            "IfcFlowTerminal",
            "IfcDistributionElement", 
            "IfcDistributionFlowElement",
            "IfcFlowController",
            "IfcFlowFitting"
        ]
    
    # Define specific keywords based on equipment function if not provided
    if equipment_keywords is None:
        equipment_function_lower = equipment_function.lower()
        if "fire extinguisher" in equipment_function_lower:
            equipment_keywords = ["extinguisher"]
        elif "fire alarm" in equipment_function_lower or "fire panel" in equipment_function_lower:
            equipment_keywords = ["fire alarm", "alarm panel", "fire panel"]
        elif "fire" in equipment_function_lower and "detector" in equipment_function_lower:
            equipment_keywords = ["smoke detector", "heat detector", "fire detector"]
        elif "sprinkler" in equipment_function_lower:
            equipment_keywords = ["sprinkler"]
        elif "pump" in equipment_function_lower:
            equipment_keywords = ["pump"]
        else:
            # For other equipment, use the function terms as keywords
            equipment_keywords = [equipment_function_lower]
    
    # Open the IFC file
    try:
        model = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        raise Exception(f"Failed to open IFC file: {e}")
    
    # List to store found equipment
    found_equipment = []
    
    # Search for elements of specified types
    for element_type in element_types:
        try:
            # Try to get elements of this type
            elements = model.by_type(element_type)
            
            # Filter elements based on keywords in their names and properties
            for element in elements:
                element_name = getattr(element, "Name", "") or ""
                element_name_lower = element_name.lower()
                
                # Check if any keyword matches the element name
                keyword_match = any(keyword.lower() in element_name_lower for keyword in equipment_keywords)
                
                # If name doesn't match, check properties for better identification
                property_match = False
                if not keyword_match:
                    try:
                        # Check element properties for matches
                        psets = ifcopenshell.util.element.get_psets(element)
                        for pset_name, pset_data in psets.items():
                            # Check property set names and values
                            if "fire" in pset_name.lower() or "alarm" in pset_name.lower():
                                property_match = True
                                break
                            for prop_name, prop_value in pset_data.items():
                                if isinstance(prop_value, str):
                                    prop_value_lower = prop_value.lower()
                                    if any(keyword.lower() in prop_value_lower for keyword in equipment_keywords):
                                        property_match = True
                                        break
                            if property_match:
                                break
                    except:
                        pass
                
                # If either name or property matches, include the element
                if keyword_match or property_match:
                    # Get spatial container information
                    container = ifcopenshell.util.element.get_container(element)
                    location_name = getattr(container, "Name", "") if container else "Unknown"
                    location_type = container.is_a() if container else "Unknown"
                    
                    # Add to found equipment list
                    found_equipment.append({
                        "name": element_name,
                        "type": element.is_a(),
                        "global_id": getattr(element, "GlobalId", ""),
                        "location": location_name,
                        "location_type": location_type
                    })
        except Exception as e:
            # Continue with next element type if current one fails
            continue
    
    # Remove duplicates based on GlobalId
    unique_equipment = []
    seen_global_ids = set()
    
    for equipment in found_equipment:
        global_id = equipment["global_id"]
        if global_id not in seen_global_ids:
            unique_equipment.append(equipment)
            seen_global_ids.add(global_id)
    
    return unique_equipment
