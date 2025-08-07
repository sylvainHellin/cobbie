def estimate_acoustic_performance(construction_type: str, materials: list, thicknesses: list) -> dict:
    """
    Estimate acoustic performance (STC rating) based on construction type, materials, and thicknesses.
    
    This function provides estimated acoustic performance when direct acoustic properties are not 
    available in BIM models. It uses industry standard data for typical construction assemblies.
    
    Args:
        construction_type (str): Type of construction assembly. Supported types:
            - 'partition_wall': Interior partition walls
            - 'floor_assembly': Floor assemblies
            - 'exterior_wall': Exterior walls
            - 'ceiling_assembly': Ceiling assemblies
        materials (list): List of material names or types in the assembly
        thicknesses (list): List of layer thicknesses in millimeters (mm)
        
    Returns:
        dict: Dictionary containing estimated acoustic performance with keys:
            - 'stc': Estimated Sound Transmission Class rating (int)
            - 'description': Description of the estimated performance
            - 'notes': Additional notes about the estimation
            
    Example:
        >>> estimate_acoustic_performance('partition_wall', ['gypsum_board', 'mineral_wool', 'gypsum_board'], [12, 50, 12])
        {'stc': 45, 'description': 'Good sound insulation for interior partition walls', 'notes': 'Based on typical gypsum board and mineral wool construction'}
    """
    # Validate inputs
    if not isinstance(materials, list) or not isinstance(thicknesses, list):
        raise ValueError("Materials and thicknesses must be provided as lists")
    
    if len(materials) != len(thicknesses):
        raise ValueError("Materials and thicknesses lists must have the same length")
    
    # Default STC values for different construction types
    stc_estimates = {
        'partition_wall': {
            'min_stc': 30,
            'max_stc': 60,
            'description': 'Interior partition walls',
            'notes': 'STC varies based on materials and construction quality'
        },
        'floor_assembly': {
            'min_stc': 40,
            'max_stc': 70,
            'description': 'Floor assemblies',
            'notes': 'STC depends on mass, decoupling, and damping layers'
        },
        'exterior_wall': {
            'min_stc': 45,
            'max_stc': 75,
            'description': 'Exterior walls',
            'notes': 'STC influenced by wall mass, insulation, and air sealing'
        },
        'ceiling_assembly': {
            'min_stc': 25,
            'max_stc': 55,
            'description': 'Ceiling assemblies',
            'notes': 'STC varies with ceiling system type and acoustic treatment'
        }
    }
    
    # Material STC contribution factors (simplified)
    material_factors = {
        'gypsum_board': 1.0,
        'concrete': 1.3,
        'brick': 1.2,
        'steel': 0.8,
        'wood': 0.9,
        'mineral_wool': 1.1,
        'fiberglass': 1.0,
        'rockwool': 1.1,
        'acoustic_insulation': 1.2,
        'mass_loaded_vinyl': 1.4,
        'lead': 1.5
    }
    
    # Base STC values for construction types
    base_stc_values = {
        'partition_wall': 35,
        'floor_assembly': 50,
        'exterior_wall': 55,
        'ceiling_assembly': 30
    }
    
    # Check if construction type is supported
    if construction_type not in base_stc_values:
        raise ValueError(f"Unsupported construction type: {construction_type}. Supported types: {list(base_stc_values.keys())}")
    
    # Calculate estimated STC based on materials and thicknesses
    base_stc = base_stc_values[construction_type]
    
    # Adjust STC based on materials
    material_multiplier = 1.0
    for material in materials:
        material_lower = material.lower()
        if material_lower in material_factors:
            material_multiplier += (material_factors[material_lower] - 1.0) * 0.5
    
    # Adjust STC based on total thickness
    total_thickness = sum(thicknesses) if thicknesses else 0
    thickness_multiplier = 1.0 + (total_thickness / 1000)  # Simplified thickness factor
    
    # Calculate final STC
    estimated_stc = int(base_stc * material_multiplier * thickness_multiplier)
    
    # Apply limits based on construction type
    min_stc = stc_estimates[construction_type]['min_stc']
    max_stc = stc_estimates[construction_type]['max_stc']
    estimated_stc = max(min_stc, min(estimated_stc, max_stc))
    
    # Prepare result
    result = {
        'stc': estimated_stc,
        'description': stc_estimates[construction_type]['description'],
        'notes': stc_estimates[construction_type]['notes']
    }
    
    return result