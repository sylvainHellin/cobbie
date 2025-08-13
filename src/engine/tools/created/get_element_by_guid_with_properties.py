import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any


def get_element_by_guid_with_properties(model_path: str, guid: str) -> Dict[str, Any]:
    """
    Retrieves an IFC element by its GlobalId and returns comprehensive information.
    
    Args:
        model_path (str): Path to the IFC model file
        guid (str): GlobalId of the element to retrieve
        
    Returns:
        Dict containing element information with keys:
            - "element_info": Basic element details (name, guid, type)
            - "direct_attributes": Dictionary of direct attribute name-value pairs
            - "property_sets": Dictionary mapping property set names to their properties
            - "type_info": Information about the element type (if applicable)
            - "container_info": Spatial container information (if available)
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Find the element by GlobalId
    element = model.by_guid(guid)
    
    if element is None:
        raise ValueError(f"No element found with GlobalId: {guid}")
    
    # 1. Basic element information
    element_info = {
        "name": element.Name if hasattr(element, "Name") else None,
        "guid": element.GlobalId,
        "type": element.is_a()
    }
    
    # 2. Direct attributes
    direct_attributes = {}
    # Get all attributes using the IfcOpenShell API
    for i in range(len(element)):
        try:
            attr = element.attribute_name(i)
            value = element[i]
            if attr not in ["Name", "GlobalId"] and value is not None:
                # Handle different attribute value types
                if isinstance(value, (int, float, str, bool)):
                    direct_attributes[attr] = value
                elif hasattr(value, "wrappedValue"):
                    direct_attributes[attr] = value.wrappedValue
                elif hasattr(value, "is_a"):
                    # For complex types, store their type and name if available
                    direct_attributes[attr] = {
                        "type": value.is_a(),
                        "name": value.Name if hasattr(value, "Name") else None,
                        "guid": value.GlobalId if hasattr(value, "GlobalId") else None
                    }
                else:
                    direct_attributes[attr] = str(value)
        except Exception:
            # Skip attributes that cause issues
            continue
    
    # 3. Property sets
    property_sets = {}
    related_properties = ifcopenshell.util.element.get_psets(element)
    if related_properties:
        property_sets = related_properties
    
    # 4. Type information
    type_info = {}
    
    # Try to get the element type using ifcopenshell.util.element.get_type first
    element_type = ifcopenshell.util.element.get_type(element)
    
    # If that doesn't work, try to find type through inverse relationships
    if not element_type:
        # Get all inverse relationships of the element
        inverses = model.get_inverse(element)
        for inverse in inverses:
            # Check if it's an IfcRelDefinesByType relationship
            if inverse.is_a("IfcRelDefinesByType"):
                element_type = inverse.RelatingType
                break
    
    if element_type:
        type_info = {
            "name": element_type.Name if hasattr(element_type, "Name") else None,
            "guid": element_type.GlobalId if hasattr(element_type, "GlobalId") else None,
            "type": element_type.is_a()
        }
        
        # Get type properties
        type_properties = ifcopenshell.util.element.get_psets(element_type)
        if type_properties:
            type_info["properties"] = type_properties
    
    # 5. Container/structure information
    container_info = {}
    container = ifcopenshell.util.element.get_container(element)
    if container:
        container_info = {
            "name": container.Name if hasattr(container, "Name") else None,
            "guid": container.GlobalId,
            "type": container.is_a()
        }
    
    # Assemble the result
    result = {
        "element_info": element_info,
        "direct_attributes": direct_attributes,
        "property_sets": property_sets,
        "type_info": type_info,
        "container_info": container_info
    }
    
    return result