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

def calculate_gross_floor_area(ifc_file_path: str) -> Dict[str, float]:
    """
    Calculate the Gross Floor Area (GFA) of a building by measuring to the outer surface 
    of exterior walls rather than simply summing individual slab areas.
    
    The GFA is calculated per building storey by:
    1. Identifying all slabs and walls in each storey
    2. Determining which walls are exterior walls
    3. Calculating the footprint area (projected area in X-Y plane) of all relevant elements
    4. Summing these areas to get the GFA for each storey
    
    This function assumes the IFC model follows standard BIM authoring practices where:
    - Building storeys are properly defined as IfcBuildingStorey entities
    - Walls and slabs are properly contained within storeys
    - Exterior walls can be identified by their composition type or properties
    
    :param ifc_file_path: Path to the IFC file
    :return: Dictionary mapping storey names to their GFA values in square meters
    """
    
    # Load the IFC model
    model = ifcopenshell.open(ifc_file_path)
    
    # Get all building storeys
    storeys = model.by_type("IfcBuildingStorey")
    
    # Dictionary to store GFA results
    gfa_results = {}
    
    # Settings for geometry creation
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    # Process each storey
    for storey in storeys:
        storey_name = storey.Name if storey.Name else f"Storey {storey.id()}"
        
        # Get all elements contained in this storey
        elements = ifcopenshell.util.element.get_decomposition(storey)
        
        # Filter for slabs and walls
        slabs = [element for element in elements if element.is_a("IfcSlab")]
        walls = [element for element in elements if element.is_a("IfcWall")]
        
        total_area = 0.0
        
        # Process slabs (typically contribute to floor area)
        for slab in slabs:
            try:
                # Create geometry for the slab
                shape = ifcopenshell.geom.create_shape(settings, slab)
                if shape:
                    # Calculate footprint area (projected area in Z direction)
                    geometry = shape.geometry
                    area = ifcopenshell.util.shape.get_footprint_area(geometry, axis="Z")
                    total_area += area
            except Exception as e:
                # Skip elements that fail geometry creation
                continue
        
        # Process walls (exterior walls contribute to GFA in some standards)
        for wall in walls:
            # Determine if wall is exterior
            is_exterior = False
            
            # Check various ways to identify exterior walls
            if hasattr(wall, 'PredefinedType') and wall.PredefinedType:
                if wall.PredefinedType.upper() in ['EXTERNAL', 'EXT']:
                    is_exterior = True
            elif hasattr(wall, 'CompositionType') and wall.CompositionType:
                if wall.CompositionType.upper() in ['EXTERNAL', 'EXT']:
                    is_exterior = True
            elif wall.Name and 'EXT' in wall.Name.upper():
                is_exterior = True
            
            # If we've determined this is an exterior wall, include its footprint
            if is_exterior:
                try:
                    # Create geometry for the wall
                    shape = ifcopenshell.geom.create_shape(settings, wall)
                    if shape:
                        # Calculate footprint area (projected area in Z direction)
                        geometry = shape.geometry
                        area = ifcopenshell.util.shape.get_footprint_area(geometry, axis="Z")
                        total_area += area
                except Exception as e:
                    # Skip elements that fail geometry creation
                    continue
        
        # Store the result
        gfa_results[storey_name] = total_area
    
    return gfa_results