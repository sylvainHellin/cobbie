
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

def validate_property_values(ifc_file_path: str) -> dict:
    """
    Validates property values in an IFC model to distinguish between placeholder values and real data.
    
    This function checks if property values are identical to their property names, which indicates
    they are placeholders rather than actual data. This is a common issue in IFC models where 
    property values equal their property names when actual data is not available.
    
    Args:
        ifc_file_path (str): Path to the IFC file to analyze
        
    Returns:
        dict: A dictionary containing:
            - 'placeholder_properties': List of properties where value equals name (placeholders)
            - 'valid_properties': List of properties with meaningful values
            - 'empty_properties': List of properties with empty/null values
            - 'summary': Summary statistics of the validation
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_file_path)
    
    # Initialize result containers
    placeholder_properties = []
    valid_properties = []
    empty_properties = []
    
    # Get all property sets
    property_sets = model.by_type("IfcPropertySet")
    
    # Iterate through all property sets
    for pset in property_sets:
        if hasattr(pset, 'HasProperties') and pset.HasProperties:
            for prop in pset.HasProperties:
                # Extract property information
                prop_name = prop.Name if hasattr(prop, 'Name') else 'Unknown'
                pset_name = pset.Name if hasattr(pset, 'Name') else 'Unknown'
                
                # Check property value
                if hasattr(prop, 'NominalValue'):
                    if prop.NominalValue is None:
                        # Empty value case
                        empty_properties.append({
                            'pset_name': pset_name,
                            'property_name': prop_name,
                            'property_value': None,
                            'property_id': prop.id()
                        })
                    else:
                        # Extract the actual value
                        if hasattr(prop.NominalValue, 'wrappedValue'):
                            prop_value = prop.NominalValue.wrappedValue
                        else:
                            prop_value = str(prop.NominalValue)
                        
                        # Check if value is identical to name (placeholder)
                        if str(prop_name) == str(prop_value):
                            placeholder_properties.append({
                                'pset_name': pset_name,
                                'property_name': prop_name,
                                'property_value': prop_value,
                                'property_id': prop.id()
                            })
                        else:
                            # Valid property with different value
                            valid_properties.append({
                                'pset_name': pset_name,
                                'property_name': prop_name,
                                'property_value': prop_value,
                                'property_id': prop.id()
                            })
    
    # Create summary statistics
    summary = {
        'total_property_sets': len(property_sets),
        'placeholder_properties_count': len(placeholder_properties),
        'valid_properties_count': len(valid_properties),
        'empty_properties_count': len(empty_properties),
        'placeholder_percentage': round(len(placeholder_properties) / (len(placeholder_properties) + len(valid_properties) + 1) * 100, 2) if (len(placeholder_properties) + len(valid_properties)) > 0 else 0
    }
    
    # Return structured result
    return {
        'placeholder_properties': placeholder_properties,
        'valid_properties': valid_properties,
        'empty_properties': empty_properties,
        'summary': summary
    }
