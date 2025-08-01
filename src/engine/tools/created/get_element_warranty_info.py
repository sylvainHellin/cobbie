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


def get_element_warranty_info(ifc_file_path: str, element_type: str) -> Dict[str, Any]:
    """
    Systematically search for warranty and guarantee-related information across all instances 
    of a specified element type in an IFC model.
    
    This function identifies elements with warranty properties, determines if those properties 
    contain actual data or placeholder values, and provides a comprehensive summary of 
    warranty information availability.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_type (str): The IFC element type to analyze (e.g., "IfcWall", "IfcSlab")
        
    Returns:
        Dict[str, Any]: A structured dictionary containing warranty information summary
    """
    # Open the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Get all elements of the specified type
    elements = ifc_file.by_type(element_type)
    
    # Initialize result structure
    result = {
        "total_elements": len(elements),
        "elements_with_warranty": 0,
        "elements_with_valid_warranty": 0,
        "warranty_property_names": set(),
        "elements_details": [],
        "summary": {}
    }
    
    # Warranty-related keywords to search for
    warranty_keywords = [
        "warranty", "guarantee", "expected life", "lifespan", "service life",
        "maintenance", "replacement", "duration", "guarantor", "start date"
    ]
    
    # Process each element
    for element in elements:
        element_info = {
            "name": getattr(element, "Name", "Unnamed"),
            "global_id": getattr(element, "GlobalId", "Unknown"),
            "property_sets": {},
            "has_warranty": False,
            "has_valid_warranty": False
        }
        
        # Get all property sets for this element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Check each property set for warranty-related properties
        for pset_name, properties in psets.items():
            warranty_properties = {}
            
            # Check each property in the property set
            for prop_name, prop_value in properties.items():
                # Check if property name contains warranty-related keywords
                if any(keyword in prop_name.lower() for keyword in warranty_keywords):
                    result["warranty_property_names"].add(prop_name)
                    warranty_properties[prop_name] = prop_value
                    
                    # Determine if the value is valid (not placeholder/empty)
                    # Improved validation to detect placeholder values
                    is_valid = (
                        prop_value is not None and 
                        prop_value != "" and 
                        str(prop_value).lower() not in ["na", "n/a", "none", "unknown", "tbd", "to be determined"] and
                        str(prop_value).lower() != prop_name.lower()  # This detects placeholder values like "WarrantyDescription" as the value
                    )
                    
                    # Add validation status
                    if is_valid:
                        warranty_properties[f"{prop_name}_status"] = "valid"
                        element_info["has_valid_warranty"] = True
                    else:
                        warranty_properties[f"{prop_name}_status"] = "placeholder/empty"
            
            # If we found warranty properties in this pset, add it to element info
            if warranty_properties:
                element_info["property_sets"][pset_name] = warranty_properties
                element_info["has_warranty"] = True
        
        # Update counts
        if element_info["has_warranty"]:
            result["elements_with_warranty"] += 1
            
        if element_info["has_valid_warranty"]:
            result["elements_with_valid_warranty"] += 1
            
        # Add element info to results if it has warranty properties
        if element_info["has_warranty"]:
            result["elements_details"].append(element_info)
    
    # Convert warranty_property_names set to list for JSON serialization
    result["warranty_property_names"] = list(result["warranty_property_names"])
    
    # Add summary statistics
    result["summary"] = {
        "total_elements": result["total_elements"],
        "elements_with_warranty": result["elements_with_warranty"],
        "elements_with_valid_warranty": result["elements_with_valid_warranty"],
        "elements_with_warranty_percentage": (result["elements_with_warranty"] / result["total_elements"] * 100) if result["total_elements"] > 0 else 0,
        "elements_with_valid_warranty_percentage": (result["elements_with_valid_warranty"] / result["total_elements"] * 100) if result["total_elements"] > 0 else 0,
        "warranty_property_sets_found": len([elem for elem in result["elements_details"] if elem["property_sets"]])
    }
    
    return result