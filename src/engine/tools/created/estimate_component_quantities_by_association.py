import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import Dict, Optional, Any

def estimate_component_quantities_by_association(
    model_path: str,
    component_type: str,
    association_rules: Optional[Dict[str, int]] = None,
    use_default_rules: bool = True
) -> Dict[str, Any]:
    """
    Estimate quantities of building components based on associations with other elements.
    
    This function estimates the quantity of building components (like doorknobs, light switches, 
    outlets, etc.) that are typically associated with other modeled elements but may not be 
    explicitly represented in the BIM model.
    
    Args:
        model_path (str): Path to the IFC model file
        component_type (str): The type of component to estimate (e.g., "doorknob", "light_switch", "outlet")
        association_rules (dict, optional): Custom rules for estimation (e.g., {"IfcDoor": 1} means 1 component per door)
        use_default_rules (bool): Whether to use built-in default estimation rules
    
    Returns:
        dict: A dictionary containing:
            - estimated_count (int): The estimated number of components
            - basis (str): Explanation of how the estimate was calculated
            - associated_elements_count (int): Number of elements used as basis for estimation
            - confidence_level (str): Confidence level of the estimate (e.g., "high", "medium", "low")
    
    Default rules:
        - doorknob: 1 per IfcDoor
        - light_switch: 1 per IfcSpace
        - outlet: 4 per IfcSpace
        - thermostat: 1 per IfcSpace with "living" or "bedroom" in name
    
    Example:
        >>> result = estimate_component_quantities_by_association("model.ifc", "doorknob")
        >>> print(result["estimated_count"])
        14
    """
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Initialize default rules
    default_rules = {
        "doorknob": {"IfcDoor": 1},
        "light_switch": {"IfcSpace": 1},
        "outlet": {"IfcSpace": 4},  # Default 4 outlets per space
        "thermostat": {"IfcSpace": 1}  # Will filter by space name
    }
    
    # Initialize variables
    estimated_count = 0
    associated_elements_count = 0
    basis = ""
    confidence_level = "low"  # Default confidence
    
    # Determine which rules to use
    rules_to_apply = {}
    if use_default_rules and component_type in default_rules:
        rules_to_apply.update(default_rules[component_type])
        confidence_level = "high"  # Higher confidence when using default rules
    
    if association_rules:
        rules_to_apply.update(association_rules)
        # If custom rules are provided, confidence might be medium unless they override defaults
        if not use_default_rules or component_type not in default_rules:
            confidence_level = "medium"
    
    # If no rules are available for this component type
    if not rules_to_apply:
        return {
            "estimated_count": 0,
            "basis": f"No rules defined for component type '{component_type}'",
            "associated_elements_count": 0,
            "confidence_level": "low"
        }
    
    # Apply rules based on component type
    if component_type == "doorknob":
        doors = model.by_type("IfcDoor")
        count_per_door = rules_to_apply.get("IfcDoor", 1)
        estimated_count = len(doors) * count_per_door
        associated_elements_count = len(doors)
        basis = f"Estimated {count_per_door} doorknob(s) per door × {len(doors)} doors"
        
    elif component_type == "light_switch":
        spaces = model.by_type("IfcSpace")
        count_per_space = rules_to_apply.get("IfcSpace", 1)
        estimated_count = len(spaces) * count_per_space
        associated_elements_count = len(spaces)
        basis = f"Estimated {count_per_space} light switch(es) per space × {len(spaces)} spaces"
        
    elif component_type == "outlet":
        spaces = model.by_type("IfcSpace")
        count_per_space = rules_to_apply.get("IfcSpace", 4)
        estimated_count = len(spaces) * count_per_space
        associated_elements_count = len(spaces)
        basis = f"Estimated {count_per_space} outlet(s) per space × {len(spaces)} spaces"
        
    elif component_type == "thermostat":
        spaces = model.by_type("IfcSpace")
        associated_spaces = []
        
        # Filter spaces with "living" or "bedroom" in name
        for space in spaces:
            if hasattr(space, 'Name') and space.Name:
                name_lower = space.Name.lower()
                if "living" in name_lower or "bedroom" in name_lower:
                    associated_spaces.append(space)
        
        count_per_space = rules_to_apply.get("IfcSpace", 1)
        estimated_count = len(associated_spaces) * count_per_space
        associated_elements_count = len(associated_spaces)
        basis = f"Estimated {count_per_space} thermostat(s) per qualifying space × {len(associated_spaces)} spaces with 'living' or 'bedroom' in name"
        if len(associated_spaces) == 0:
            confidence_level = "low"
        
    else:
        # For custom component types, apply generic rules
        total_count = 0
        total_elements = 0
        basis_parts = []
        
        for element_type, count_per_element in rules_to_apply.items():
            elements = model.by_type(element_type)
            type_count = len(elements) * count_per_element
            total_count += type_count
            total_elements += len(elements)
            basis_parts.append(f"{count_per_element} per {element_type} × {len(elements)} elements")
        
        estimated_count = total_count
        associated_elements_count = total_elements
        basis = "; ".join(basis_parts)
        if total_elements > 0:
            confidence_level = "medium"
    
    return {
        "estimated_count": estimated_count,
        "basis": basis,
        "associated_elements_count": associated_elements_count,
        "confidence_level": confidence_level
    }