
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

def calculate_element_volume_from_geometry(ifc_file_path: str, element_guid: str) -> float:
    """
    Calculate the volume of an IFC element based on its geometric representation.
    
    This function computes volume directly from the element's geometry (SweptSolid, 
    SurfaceModel, etc.) rather than relying on pre-computed volume properties.
    It uses IfcOpenShell's geometry processing capabilities to create a mesh or solid
    geometry and then calculates the volume directly from that representation.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_guid (str): GlobalId of the IFC element
        
    Returns:
        float: Volume of the element in cubic meters. Returns 0.0 if no volume can be calculated.
        
    Raises:
        ValueError: If element not found or has no geometry
        FileNotFoundError: If the IFC file cannot be found
        Exception: If geometry processing fails
    """
    try:
        # Load the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"IFC file not found at path: {ifc_file_path}")
    except Exception as e:
        raise Exception(f"Failed to open IFC file: {str(e)}")
    
    # Find the element by GUID
    try:
        element = ifc_file.by_guid(element_guid)
    except Exception:
        raise ValueError(f"Element with GUID {element_guid} not found")
    
    if element is None:
        raise ValueError(f"Element with GUID {element_guid} not found")
    
    # Check if element has representation
    if not hasattr(element, 'Representation') or not element.Representation:
        raise ValueError(f"Element {element_guid} has no geometric representation")
    
    # Create geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    try:
        # Create shape geometry from the element
        shape = ifcopenshell.geom.create_shape(settings, element)
        
        # Check if shape was created successfully
        if shape is None:
            raise Exception(f"Failed to create geometry shape for element {element_guid}")
        
        # Get the geometry from the shape
        geometry = shape.geometry
        
        # Check if geometry exists
        if geometry is None:
            raise Exception(f"No geometry data available for element {element_guid}")
        
        # Calculate volume using IfcOpenShell's utility function
        volume = ifcopenshell.util.shape.get_volume(geometry)
        
        # Handle case where volume calculation returns None or invalid value
        if volume is None:
            return 0.0
            
        return float(volume)
        
    except Exception as e:
        raise Exception(f"Failed to calculate volume for element {element_guid}: {str(e)}")
