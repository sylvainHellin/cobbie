
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

def get_element_structural_type(element: ifcopenshell.entity_instance) -> str:
    """
    Determine the structural type classification of a building element based on its IFC data.
    
    This function analyzes element names and property sets to classify structural elements
    into specific types like 'flat wood-joist structure', 'truss structure', 'rafter structure'.
    
    Assumptions:
    - This function works with IFC models exported from Revit, which use PSet_Revit_* property sets
    - Structural type information is often embedded in element names
    - Property sets may contain structural classification information
    
    Args:
        element: An IFC element instance (IfcSlab, IfcRoof, IfcBeam, etc.)
        
    Returns:
        str: Structural type classification such as:
            - 'flat wood-joist structure'
            - 'truss structure'
            - 'rafter structure'
            - 'concrete slab structure'
            - 'steel frame structure'
            - 'unknown structure' (if no classification can be determined)
    """
    # Get element name
    element_name = element.Name if element.Name else ""
    element_name_lower = element_name.lower()
    
    # Get all property sets
    property_sets = ifcopenshell.util.element.get_psets(element)
    
    # Check name for structural type keywords
    # Wood joist structures
    if any(keyword in element_name_lower for keyword in ["wood joist", "timber joist", "joist"]):
        if "flat" in element_name_lower or "flat" in str(property_sets).lower():
            return "flat wood-joist structure"
        else:
            return "wood-joist structure"
    
    # Truss structures
    if "truss" in element_name_lower:
        return "truss structure"
    
    # Rafter structures
    if "rafter" in element_name_lower:
        return "rafter structure"
    
    # Concrete slab structures
    if any(keyword in element_name_lower for keyword in ["concrete", "slab"]):
        if "flat" in element_name_lower:
            return "flat concrete slab structure"
        else:
            return "concrete slab structure"
    
    # Steel frame structures
    if any(keyword in element_name_lower for keyword in ["steel", "wide flange", "w-flange"]):
        return "steel frame structure"
    
    # Check property sets for structural information
    for pset_name, pset_data in property_sets.items():
        # Check if this is a structural property set
        if "structural" in pset_name.lower():
            # Look for structural type information in property set values
            for prop_name, prop_value in pset_data.items():
                if isinstance(prop_value, str):
                    prop_value_lower = prop_value.lower()
                    if "wood joist" in prop_value_lower:
                        return "wood-joist structure"
                    elif "truss" in prop_value_lower:
                        return "truss structure"
                    elif "rafter" in prop_value_lower:
                        return "rafter structure"
                    elif "concrete" in prop_value_lower:
                        return "concrete slab structure"
                    elif "steel" in prop_value_lower:
                        return "steel frame structure"
    
    # Check for classification information in property sets
    for pset_name, pset_data in property_sets.items():
        if "type" in pset_name.lower() or "identity" in pset_name.lower():
            for prop_name, prop_value in pset_data.items():
                if "classification" in prop_name.lower() and isinstance(prop_value, str):
                    if "joist" in prop_value.lower():
                        return "wood-joist structure"
                    elif "truss" in prop_value.lower():
                        return "truss structure"
                    elif "rafter" in prop_value.lower():
                        return "rafter structure"
    
    # If no specific structural type can be determined
    return "unknown structure"
