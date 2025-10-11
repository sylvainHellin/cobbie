import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
from collections import defaultdict
import math
from typing import Dict, Any, List, Tuple

def calculate_structural_efficiency_metrics(model_path: str) -> Dict[str, Any]:
    """
    Calculate structural efficiency metrics for an IFC building model.
    
    This function analyzes the distribution of structural elements, calculates
    efficiency ratios, and provides an assessment of the structural system's
    efficiency based on established engineering metrics.
    
    Args:
        model_path: Path to the IFC model file
        
    Returns:
        Dictionary containing:
        - total_structural_elements: Total count of structural elements
        - element_counts: Dictionary with counts by type
        - element_ratios: Percentage breakdown of each element type
        - system_type: Identified structural system type
        - efficiency_rating: Overall efficiency assessment
        - building_characteristics: Number of stories, grid regularity, etc.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Define main structural element types for efficiency analysis
    main_structural_types = ['IfcBeam', 'IfcColumn', 'IfcSlab']
    all_structural_types = ['IfcBeam', 'IfcColumn', 'IfcSlab', 'IfcWall', 'IfcFooting', 
                           'IfcPile', 'IfcPlate', 'IfcMember']
    
    # Count structural elements
    element_counts = {}
    total_structural_elements = 0
    
    for element_type in all_structural_types:
        count = len(model.by_type(element_type))
        element_counts[element_type] = count
        total_structural_elements += count
    
    # Calculate element ratios for main structural elements
    main_total = sum(element_counts[elem_type] for elem_type in main_structural_types)
    element_ratios = {}
    
    for element_type in main_structural_types:
        ratio = (element_counts[element_type] / main_total * 100) if main_total > 0 else 0
        element_ratios[element_type] = round(ratio, 1)
    
    # Analyze building characteristics
    building_characteristics = {}
    
    # Count building stories
    stories = model.by_type('IfcBuildingStorey')
    building_characteristics['number_of_stories'] = len(stories)
    building_characteristics['story_elevations'] = []
    
    for story in stories:
        elevation = getattr(story, 'Elevation', 0)
        building_characteristics['story_elevations'].append(float(elevation))
    
    # Analyze grid regularity through column positioning
    columns = model.by_type('IfcColumn')
    column_positions = []
    
    for column in columns:
        try:
            placement = column.ObjectPlacement
            if placement and hasattr(placement, 'RelativePlacement'):
                rel_placement = placement.RelativePlacement
                if hasattr(rel_placement, 'Location'):
                    location = rel_placement.Location
                    if hasattr(location, 'Coordinates'):
                        coords = location.Coordinates
                        if len(coords) >= 2:
                            column_positions.append((float(coords[0]), float(coords[1])))
        except Exception:
            continue
    
    # Calculate grid regularity metrics
    grid_regularity = "irregular"
    if len(column_positions) > 4:
        x_coords = [pos[0] for pos in column_positions]
        y_coords = [pos[1] for pos in column_positions]
        
        # Check for regular spacing patterns
        x_unique = sorted(list(set([round(x, 2) for x in x_coords])))
        y_unique = sorted(list(set([round(y, 2) for y in y_coords])))
        
        if len(x_unique) > 1 and len(y_unique) > 1:
            # Calculate spacing consistency
            x_spacings = [x_unique[i+1] - x_unique[i] for i in range(len(x_unique)-1)]
            y_spacings = [y_unique[i+1] - y_unique[i] for i in range(len(y_unique)-1)]
            
            x_var = max(x_spacings) - min(x_spacings) if x_spacings else 0
            y_var = max(y_spacings) - min(y_spacings) if y_spacings else 0
            
            if x_var < 0.5 and y_var < 0.5:  # Threshold for regular spacing
                grid_regularity = "regular"
            elif x_var < 1.0 and y_var < 1.0:
                grid_regularity = "semi-regular"
    
    building_characteristics['grid_regularity'] = grid_regularity
    building_characteristics['column_count'] = len(columns)
    building_characteristics['beam_count'] = element_counts['IfcBeam']
    building_characteristics['slab_count'] = element_counts['IfcSlab']
    
    # Identify structural system type
    system_type = "unknown"
    
    # Analyze element distribution to determine system type
    beam_ratio = element_ratios.get('IfcBeam', 0)
    column_ratio = element_ratios.get('IfcColumn', 0)
    slab_ratio = element_ratios.get('IfcSlab', 0)
    wall_count = element_counts.get('IfcWall', 0)
    
    if column_ratio > 50 and beam_ratio > 10 and slab_ratio > 15:
        if wall_count > element_counts['IfcColumn']:
            system_type = "dual_system"  # Frame + shear walls
        else:
            system_type = "frame_system"
    elif wall_count > 50:
        system_type = "shear_wall_system"
    elif slab_ratio > 40:
        system_type = "flat_plate_system"
    elif beam_ratio > 30:
        system_type = "beam_and_slab_system"
    else:
        system_type = "mixed_system"
    
    # Calculate efficiency rating based on system type and element ratios
    efficiency_rating = "moderate"  # Default rating
    efficiency_score = 50  # Base score out of 100
    
    # Efficiency criteria based on structural system type
    if system_type == "frame_system":
        # Ideal ratios for frame systems: ~15% beams, ~65% columns, ~20% slabs
        ideal_beam, ideal_column, ideal_slab = 15, 65, 20
        efficiency_score = 100 - (abs(beam_ratio - ideal_beam) * 2 + 
                                 abs(column_ratio - ideal_column) * 1.5 + 
                                 abs(slab_ratio - ideal_slab) * 2)
    
    elif system_type == "shear_wall_system":
        # More walls, fewer columns expected
        efficiency_score = 70 if wall_count > 100 else 50
    
    elif system_type == "dual_system":
        # Balanced distribution between frame and walls
        efficiency_score = 80 if grid_regularity == "regular" else 60
    
    # Adjust for building height
    if building_characteristics['number_of_stories'] > 10:
        efficiency_score -= 10  # Tall buildings are more complex
    elif building_characteristics['number_of_stories'] < 3:
        efficiency_score += 10  # Simple buildings are more efficient
    
    # Adjust for grid regularity
    if grid_regularity == "regular":
        efficiency_score += 10
    elif grid_regularity == "irregular":
        efficiency_score -= 15
    
    # Determine final efficiency rating
    efficiency_score = max(0, min(100, efficiency_score))
    
    if efficiency_score >= 85:
        efficiency_rating = "excellent"
    elif efficiency_score >= 70:
        efficiency_rating = "good"
    elif efficiency_score >= 55:
        efficiency_rating = "moderate"
    elif efficiency_score >= 40:
        efficiency_rating = "poor"
    else:
        efficiency_rating = "inefficient"
    
    # Get material information for additional context
    materials = model.by_type('IfcMaterial')
    material_types = set()
    for material in materials:
        if material.Name:
            material_types.add(material.Name)
    
    building_characteristics['material_types'] = list(material_types)[:10]  # Limit to first 10
    
    # Compile results
    result = {
        'total_structural_elements': total_structural_elements,
        'element_counts': element_counts,
        'element_ratios': element_ratios,
        'system_type': system_type,
        'efficiency_rating': efficiency_rating,
        'efficiency_score': round(efficiency_score, 1),
        'building_characteristics': building_characteristics,
        'analysis_summary': {
            'main_structural_elements': main_total,
            'primary_system_components': f"Columns ({column_ratio}%), Beams ({beam_ratio}%), Slabs ({slab_ratio}%)",
            'design_complexity': 'high' if grid_regularity == 'irregular' else 'low' if grid_regularity == 'regular' else 'medium'
        }
    }
    
    return result