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


def get_door_width_by_guid(model_path: str, guid: str) -> Dict[str, Any]:
    """
    Retrieve door width by GlobalId from an IFC model.
    
    This function searches for width-related properties across multiple sources:
    - OverallWidth from direct attributes (highest confidence)
    - Width from PSet_Revit_Type_Dimensions (medium confidence)
    - Other width-related properties from various property sets (low confidence)
    
    Note: This function assumes the IFC model was exported from Revit and may contain
    Revit-specific property sets like PSet_Revit_Type_Dimensions.
    
    Args:
        model_path (str): Path to the IFC model file
        guid (str): GlobalId of the door element
        
    Returns:
        Dict[str, Any]: Dictionary containing:
            - width (float): Width value in meters (0.0 if not found)
            - source (str): Source property name ("none" if not found)
            - confidence (str): "high", "medium", "low", or "none"
            - all_sources (dict): All found width sources for verification
    """
    # Initialize result structure
    result = {
        "width": 0.0,
        "source": "none",
        "confidence": "none",
        "all_sources": {}
    }
    
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
        
        # Find the element by GUID
        element = model.by_guid(guid)
        
        # Verify it's a door
        if not element or not element.is_a('IfcDoor'):
            return result
            
        # Collect all width sources
        width_sources = {}
        
        # 1. Check direct attributes (highest confidence)
        if hasattr(element, 'OverallWidth') and element.OverallWidth is not None:
            overall_width = element.OverallWidth
            try:
                width_value = float(overall_width)
                width_sources["OverallWidth"] = {
                    "value": width_value,
                    "confidence": "high",
                    "unit": "meters"
                }
            except (ValueError, TypeError):
                pass  # Skip if cannot convert to float
        
        # 2. Check property sets
        if hasattr(element, 'IsDefinedBy') and element.IsDefinedBy:
            for rel in element.IsDefinedBy:
                if rel.is_a('IfcRelDefinesByProperties'):
                    pset = rel.RelatingPropertyDefinition
                    if hasattr(pset, 'HasProperties') and pset.HasProperties:
                        pset_name = getattr(pset, 'Name', 'Unknown')
                        
                        for prop in pset.HasProperties:
                            if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                prop_name = prop.Name
                                
                                # Check for width-related properties
                                if prop_name.lower() in ['width', 'overallwidth'] or 'width' in prop_name.lower():
                                    # Extract the actual value from NominalValue
                                    try:
                                        # Get the wrapped value - this is the key fix
                                        if hasattr(prop.NominalValue, 'wrappedValue'):
                                            prop_value = prop.NominalValue.wrappedValue
                                        else:
                                            prop_value = prop.NominalValue
                                        
                                        # Check if value is numeric
                                        if isinstance(prop_value, (int, float)):
                                            width_value = float(prop_value)
                                            
                                            # Determine confidence based on property set
                                            confidence = "low"
                                            if pset_name == 'PSet_Revit_Type_Dimensions':
                                                confidence = "medium"
                                            elif 'dimension' in pset_name.lower():
                                                confidence = "medium"
                                            elif pset_name == 'Pset_DoorCommon':
                                                confidence = "medium"
                                            
                                            # Check if value might be in millimeters (convert if > 10)
                                            unit = "meters"
                                            if width_value > 10:  # Likely in mm
                                                width_value = width_value / 1000.0  # Convert to meters
                                                unit = "millimeters (converted to meters)"
                                            
                                            width_sources[f"{pset_name}.{prop_name}"] = {
                                                "value": width_value,
                                                "confidence": confidence,
                                                "unit": unit
                                            }
                                    except (ValueError, TypeError, AttributeError):
                                        # Skip if cannot convert to float or access wrappedValue
                                        continue
        
        # Store all sources for verification
        result["all_sources"] = width_sources
        
        # Select the best width source based on confidence hierarchy
        if width_sources:
            # Priority: high > medium > low
            best_source = None
            best_confidence = "none"
            
            for source_name, source_data in width_sources.items():
                confidence = source_data["confidence"]
                
                # Update if this source has higher confidence
                if (best_confidence == "none" or
                    (confidence == "high" and best_confidence != "high") or
                    (confidence == "medium" and best_confidence in ["none", "low"]) or
                    (confidence == "low" and best_confidence == "none")):
                    best_source = source_name
                    best_confidence = confidence
            
            if best_source:
                result["width"] = width_sources[best_source]["value"]
                result["source"] = best_source
                result["confidence"] = best_confidence
        
        return result
        
    except Exception:
        # Handle errors gracefully by returning default result
        return result