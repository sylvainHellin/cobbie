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

def calculate_embodied_carbon_of_structural_elements(
    ifc_file_path: str,
    element_types: Optional[List[str]] = None,
    carbon_database: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate the embodied carbon of structural elements in an IFC model.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_types (List[str], optional): Specific structural element types to analyze 
            (e.g., ['IfcBeam', 'IfcColumn']). If None, analyze all structural elements.
        carbon_database (str, optional): Path to a carbon factor database or identifier for 
            which database to use (e.g., 'EC3', 'ICE'). If None, use a default database.
            
    Returns:
        Dict[str, Any]: A dictionary containing:
          - 'elements': List of dictionaries with element information and carbon data
          - 'total_carbon': Total embodied carbon of all analyzed elements (kg CO2e)
          - 'carbon_by_type': Dictionary mapping element types to their total carbon
          - 'carbon_by_material': Dictionary mapping materials to their total carbon
          - 'assumptions': List of assumptions made during the calculation
          - 'limitations': List of limitations of the analysis
          
    Assumptions:
        - This function assumes the IFC model contains valid geometry representations
        - Material quantities are derived from element volumes
        - Standard material densities are used when not specified in the model
        - Carbon factors are in kg CO2e per kg of material unless otherwise specified
        
    Limitations:
        - Carbon factors are simplified and may not reflect project-specific values
        - Complex material compositions might not be fully captured
        - Geometry calculations may fail for non-manifold shapes
    """
    
    # Default structural element types if none specified
    if element_types is None:
        element_types = [
            "IfcBeam", "IfcColumn", "IfcSlab", "IfcWall", 
            "IfcWallStandardCase", "IfcFooting", "IfcPile", 
            "IfcStructuralItem"
        ]
    
    # Default carbon factors (kg CO2e per kg of material)
    # These are simplified values for demonstration purposes
    default_carbon_factors = {
        "Concrete": 0.13,  # kg CO2e/kg
        "Steel": 1.85,     # kg CO2e/kg
        "Timber": -0.5,    # kg CO2e/kg (carbon sequestration)
        "Aluminum": 8.2,   # kg CO2e/kg
        "Brick": 0.21,     # kg CO2e/kg
        "Glass": 1.2,      # kg CO2e/kg
        "Insulation": 2.0, # kg CO2e/kg (generic)
    }
    
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Initialize results
    elements_data = []
    total_carbon = 0.0
    carbon_by_type = {}
    carbon_by_material = {}
    assumptions = [
        "Material quantities are derived from element volumes calculated from geometry",
        "Standard material densities are used when not specified in the model",
        "Carbon factors are simplified and may not reflect project-specific values",
        "Geometry calculations assume valid manifold shapes"
    ]
    limitations = [
        "Carbon factors are simplified and may not reflect project-specific values",
        "Complex material compositions might not be fully captured",
        "Geometry calculations may fail for non-manifold shapes",
        "Only considers structural elements, not finishes or MEP components"
    ]
    
    # Process each element type
    for element_type in element_types:
        elements = ifc_file.by_type(element_type)
        
        for element in elements:
            element_carbon = 0.0
            element_materials = []
            
            # Get materials for the element
            materials = ifcopenshell.util.element.get_materials(element, should_inherit=True)
            
            if not materials:
                # Skip elements with no materials
                continue
                
            # Calculate volume if possible
            volume = None
            try:
                # Try to get the shape representation
                if hasattr(element, 'Representation') and element.Representation:
                    # Create a shape for volume calculation
                    settings = ifcopenshell.geom.settings()
                    shape = ifcopenshell.geom.create_shape(settings, element)
                    if shape:
                        geometry = shape.geometry
                        volume = ifcopenshell.util.shape.get_volume(geometry)
            except Exception:
                # Volume calculation failed
                pass
            
            # Process each material
            for material in materials:
                material_name = getattr(material, 'Name', 'Unknown')
                if not material_name:
                    material_name = material.is_a()
                    
                # Get material density
                density = None
                try:
                    density = ifcopenshell.util.element.get_element_mass_density(element)
                except Exception:
                    # Use default densities if not available
                    default_densities = {
                        "Concrete": 2400,  # kg/m³
                        "Steel": 7850,     # kg/m³
                        "Timber": 500,     # kg/m³
                        "Aluminum": 2700,  # kg/m³
                        "Brick": 1800,     # kg/m³
                        "Glass": 2500,     # kg/m³
                    }
                    
                    # Try to match material name with default densities
                    for key, value in default_densities.items():
                        if key.lower() in material_name.lower():
                            density = value
                            break
                
                # Calculate mass if volume and density are available
                mass = None
                if volume is not None and density is not None:
                    mass = volume * density
                
                # Get carbon factor
                carbon_factor = None
                for key, value in default_carbon_factors.items():
                    if key.lower() in material_name.lower():
                        carbon_factor = value
                        break
                
                # If no specific factor found, use a generic one
                if carbon_factor is None:
                    carbon_factor = 1.0  # Default fallback
                    assumptions.append(f"Using default carbon factor of 1.0 for material: {material_name}")
                
                # Calculate carbon for this material
                material_carbon = 0.0
                if mass is not None:
                    material_carbon = mass * carbon_factor / 1000  # Convert to kg CO2e
                elif volume is not None:
                    # If we only have volume, use a density of 1000 kg/m³ as fallback
                    material_carbon = volume * 1000 * carbon_factor / 1000
                    assumptions.append(f"Using default density of 1000 kg/m³ for material: {material_name}")
                
                element_carbon += material_carbon
                
                # Store material data
                material_data = {
                    "name": material_name,
                    "volume": volume,
                    "mass": mass,
                    "density": density,
                    "carbon_factor": carbon_factor,
                    "carbon": material_carbon
                }
                element_materials.append(material_data)
                
                # Update carbon by material
                if material_name in carbon_by_material:
                    carbon_by_material[material_name] += material_carbon
                else:
                    carbon_by_material[material_name] = material_carbon
            
            # Store element data
            element_data = {
                "guid": getattr(element, 'GlobalId', 'N/A'),
                "type": element.is_a(),
                "name": getattr(element, 'Name', 'N/A'),
                "volume": volume,
                "carbon": element_carbon,
                "materials": element_materials
            }
            elements_data.append(element_data)
            
            # Update totals
            total_carbon += element_carbon
            
            # Update carbon by type
            element_type_name = element.is_a()
            if element_type_name in carbon_by_type:
                carbon_by_type[element_type_name] += element_carbon
            else:
                carbon_by_type[element_type_name] = element_carbon
    
    # Prepare result dictionary
    result = {
        "elements": elements_data,
        "total_carbon": total_carbon,
        "carbon_by_type": carbon_by_type,
        "carbon_by_material": carbon_by_material,
        "assumptions": assumptions,
        "limitations": limitations
    }
    
    return result