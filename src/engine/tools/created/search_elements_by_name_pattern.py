
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def search_elements_by_name_pattern(
    ifc_file_path: str, 
    name_pattern: str, 
    element_types: Optional[List[str]] = None, 
    case_sensitive: bool = False, 
    include_spatial_info: bool = True
) -> List[Dict[str, Any]]:
    """
    Search for IFC elements whose names match a given pattern.
    
    Args:
        ifc_file_path: Path to the IFC file to search in
        name_pattern: The text pattern to search for in element names
        element_types: List of IFC element types to search within. If None, searches all element types.
        case_sensitive: Whether the search should be case-sensitive
        include_spatial_info: Whether to include spatial container information
        
    Returns:
        List of dictionaries containing information about matching elements:
        - element_name (str): The element's name
        - element_type (str): The IFC type of the element
        - element_guid (str): The element's GlobalId
        - spatial_info (Dict[str, str], optional): Spatial container information if include_spatial_info is True
        - element_object (ifcopenshell.entity_instance): The actual IFC element object
    """
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        # Return empty list if file cannot be opened
        return []
    
    # Get all element types if not specified
    if element_types is None:
        # For simplicity, we'll search common element types
        element_types = [
            "IfcElement", "IfcBuildingElement", "IfcFlowTerminal", 
            "IfcFlowFitting", "IfcFlowSegment", "IfcDistributionElement",
            "IfcFurnishingElement", "IfcEquipmentElement"
        ]
    
    # Prepare the name pattern for comparison
    search_pattern = name_pattern if case_sensitive else name_pattern.lower()
    
    results = []
    
    # Search through each specified element type
    for element_type in element_types:
        try:
            elements = ifc_file.by_type(element_type)
        except:
            # Skip if element type doesn't exist in this schema
            continue
            
        for element in elements:
            # Get element name, handling cases where it might not exist
            element_name = getattr(element, 'Name', None)
            if element_name is None:
                continue
                
            # Check if name matches pattern
            element_name_for_comparison = element_name if case_sensitive else element_name.lower()
            if search_pattern in element_name_for_comparison:
                # Create result entry
                result_entry = {
                    "element_name": element_name,
                    "element_type": element.is_a(),
                    "element_guid": getattr(element, 'GlobalId', ''),
                    "element_object": element
                }
                
                # Add spatial information if requested
                if include_spatial_info:
                    try:
                        container = ifcopenshell.util.element.get_container(element)
                        if container:
                            result_entry["spatial_info"] = {
                                "container_name": getattr(container, 'Name', ''),
                                "container_type": container.is_a()
                            }
                        else:
                            result_entry["spatial_info"] = {
                                "container_name": "",
                                "container_type": ""
                            }
                    except:
                        result_entry["spatial_info"] = {
                            "container_name": "",
                            "container_type": ""
                        }
                
                results.append(result_entry)
    
    return results
