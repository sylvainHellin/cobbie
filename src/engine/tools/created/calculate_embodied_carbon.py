import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Union, Optional

def calculate_embodied_carbon(
    model_path: str,
    element_types: Optional[List[str]] = None,
    carbon_factors: Optional[Dict[str, float]] = None
) -> Dict[str, Union[float, Dict[str, float]]]:
    """
    Calculate the embodied carbon of building elements in an IFC model.
    
    This function calculates material volumes for specified elements and applies
    carbon factors to estimate embodied carbon. It's designed for IFC models
    exported from BIM authoring software like Revit.
    
    Args:
        model_path (str): Path to the IFC model file.
        element_types (List[str], optional): List of element types to process.
            Defaults to ['IfcBeam', 'IfcColumn', 'IfcSlab', 'IfcWall'].
        carbon_factors (Dict[str, float], optional): Mapping of material names to 
            carbon factors (kgCO2e per cubic meter). If not provided, a default
            database of common construction materials is used.
            
    Returns:
        Dict[str, Union[float, Dict[str, float]]]: A dictionary containing:
            - 'total_carbon': Total embodied carbon in kgCO2e
            - 'material_breakdown': Breakdown of carbon by material in kgCO2e
            
    Raises:
        ValueError: If no carbon factors are provided and no default factors 
            are available for the materials in the model.
            
    Note:
        This function assumes IFC models exported from Revit with PSet_Revit_Dimensions
        containing volume information. For other software, geometry-based volume
        calculation may be needed.
    """
    
    # Default element types for structural elements
    if element_types is None:
        element_types = ['IfcBeam', 'IfcColumn', 'IfcSlab', 'IfcWall']
    
    # Default carbon factors for common construction materials (kgCO2e per m³)
    default_carbon_factors = {
        'Concrete': 350.0,
        'Reinforced Concrete': 400.0,
        'Steel': 1500.0,
        'Metal': 1500.0,  # More general term
        'Aluminum': 2000.0,
        'Timber': 100.0,
        'Wood': 100.0,  # Alternative term
        'Brick': 200.0,
        'Block': 150.0,
        'Glass': 1000.0,
        'Insulation': 50.0,
        'Gypsum': 100.0,
        'Plasterboard': 100.0,  # Specific to wall layers
        'Masonry': 200.0,  # For concrete blocks
        'CMU': 200.0,  # Concrete masonry unit
    }
    
    # Use provided carbon factors or default ones
    if carbon_factors is None:
        carbon_factors = default_carbon_factors
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Initialize results
    total_carbon = 0.0
    material_breakdown = {}
    missing_factors = set()
    
    # Process each element type
    for element_type in element_types:
        elements = model.by_type(element_type)
        
        for element in elements:
            # Get material information
            material_names = []
            material = ifcopenshell.util.element.get_material(element)
            
            if material:
                if hasattr(material, 'Name') and material.Name:
                    material_names.append(material.Name)
                elif hasattr(material, 'ForLayerSet') and material.ForLayerSet:
                    # Handle material layer sets
                    layers = material.ForLayerSet.MaterialLayers
                    for layer in layers:
                        if layer.Material and layer.Material.Name:
                            material_names.append(layer.Material.Name)
                elif hasattr(material, 'Materials') and material.Materials:
                    # Handle material lists
                    for mat in material.Materials:
                        if hasattr(mat, 'Name') and mat.Name:
                            material_names.append(mat.Name)
            
            # If no material names found, use a generic name based on element type
            if not material_names:
                material_names.append(f"Unknown {element_type} Material")
            
            # Get volume from PSet_Revit_Dimensions
            volume = 0.0
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Look for volume in PSet_Revit_Dimensions
            dimensions_pset = psets.get('PSet_Revit_Dimensions', {})
            if 'Volume' in dimensions_pset:
                try:
                    volume = float(dimensions_pset['Volume'])
                except (ValueError, TypeError):
                    pass
            
            if volume > 0:
                # Process each material name
                for material_name in material_names:
                    # Apply carbon factor
                    carbon_factor = None
                    
                    # Try to find a matching carbon factor (case insensitive)
                    for factor_material_name, factor_value in carbon_factors.items():
                        if factor_material_name.lower() in material_name.lower() or \
                           material_name.lower() in factor_material_name.lower():
                            carbon_factor = factor_value
                            break
                    
                    # If no exact match, try with default factors
                    if carbon_factor is None:
                        for factor_material_name, factor_value in default_carbon_factors.items():
                            if factor_material_name.lower() in material_name.lower() or \
                               material_name.lower() in factor_material_name.lower():
                                carbon_factor = factor_value
                                break
                    
                    if carbon_factor is not None:
                        element_carbon = volume * carbon_factor
                        total_carbon += element_carbon
                        
                        # Update material breakdown
                        if material_name in material_breakdown:
                            material_breakdown[material_name] += element_carbon
                        else:
                            material_breakdown[material_name] = element_carbon
                    else:
                        # Track materials with missing carbon factors
                        missing_factors.add(material_name)
    
    # If we have materials with missing factors and no user-provided factors, raise an error
    if missing_factors and carbon_factors == default_carbon_factors:
        raise ValueError(
            f"Carbon factors needed for materials: {', '.join(missing_factors)}. "
            "Please provide a carbon_factors dictionary with factors for these materials."
        )
    
    return {
        'total_carbon': total_carbon,
        'material_breakdown': material_breakdown
    }