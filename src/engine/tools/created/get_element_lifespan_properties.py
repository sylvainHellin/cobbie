
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

def get_element_lifespan_properties(ifc_file_path: str, element: ifcopenshell.entity_instance) -> Dict[str, Any]:
    """
    Search for lifespan-related properties associated with an IFC element.
    
    This function looks for various common property names related to lifespan/expected life
    across different property sets that might contain this information, including Revit-specific
    property sets.
    
    Args:
        ifc_file_path (str or ifcopenshell.file): Path to the IFC file or the IFC model object
        element (ifcopenshell.entity_instance): The IFC element to search properties for
        
    Returns:
        Dict[str, Any]: Dictionary mapping found property names to their actual values
    """
    # Common lifespan property names to search for
    lifespan_property_names = [
        'ExpectedLife', 'ServiceLife', 'DesignLife', 'UsefulLife', 'Lifetime',
        'Expected Life', 'Service Life', 'Design Life', 'Useful Life',
        'WarrantyStartDate', 'WarrantyDurationLabor', 'WarrantyDurationParts',
        'WarrantyGuarantorLabor', 'WarrantyGuarantorParts', 'WarrantyDescription'
    ]
    
    # Load the IFC file if a path is provided, otherwise use the model object
    if isinstance(ifc_file_path, str):
        try:
            model = ifcopenshell.open(ifc_file_path)
        except Exception as e:
            raise Exception(f"Error loading IFC file: {e}")
    else:
        model = ifc_file_path
    
    # Get all property sets for the element
    try:
        psets = ifcopenshell.util.element.get_psets(element)
    except Exception as e:
        raise Exception(f"Error getting property sets: {e}")
    
    # Dictionary to store found lifespan properties
    lifespan_properties = {}
    
    # Convert property names to lowercase for case-insensitive comparison
    lifespan_property_names_lower = [name.lower() for name in lifespan_property_names]
    
    # Iterate through all property sets
    for pset_name, pset_properties in psets.items():
        # Check for lifespan properties in this property set
        for prop_name, prop_value in pset_properties.items():
            # Check if property name matches any of our lifespan property names (case-insensitive)
            if prop_name.lower() in lifespan_property_names_lower:
                # Filter out placeholder values (where value equals property name or is None)
                if (prop_value is not None and 
                    str(prop_value).lower() != prop_name.lower() and
                    str(prop_value).strip() != '' and  # Filter out empty strings
                    str(prop_value).strip().lower() not in ['none', 'n/a', 'na', 'null'] and  # Filter out common null values
                    str(prop_value) != str(prop_name)):  # Direct comparison as well
                    # Add to our results with the original property name
                    lifespan_properties[prop_name] = prop_value
    
    return lifespan_properties
