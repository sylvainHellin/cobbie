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


def get_comprehensive_wall_analysis(model_path: str) -> Dict[str, Any]:
    """
    Provides comprehensive analysis of all wall types in an IFC model.
    
    Args:
        model_path: Path to the IFC model file
        
    Returns:
        Dictionary containing:
        - total_walls: Total count of all wall entities
        - wall_type_counts: Dictionary of wall type names with counts and percentages
        - wall_type_details: Detailed information for each wall type including:
          - count: Number of instances
          - percentage: Percentage of total walls
          - thickness: Wall thickness if available
          - material_layers: List of material layers with names and thicknesses
          - entity_types: List of IFC entity types included (IfcWall, IfcWallStandardCase)
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all wall entities
    walls = model.by_type('IfcWall')
    wall_standard_cases = model.by_type('IfcWallStandardCase')
    all_walls = walls + wall_standard_cases
    
    # Group walls by type name
    wall_types = {}
    for wall in all_walls:
        if wall.Name:
            # Extract wall type from name (format: "Basic Wall:Type Name:ID")
            parts = wall.Name.split(':')
            if len(parts) >= 2:
                wall_type = parts[1].strip()
                if wall_type not in wall_types:
                    wall_types[wall_type] = []
                wall_types[wall_type].append(wall)
    
    total_walls = len(all_walls)
    
    # Prepare results
    wall_type_counts = {}
    wall_type_details = {}
    
    for wall_type_name, wall_list in wall_types.items():
        count = len(wall_list)
        percentage = (count / total_walls) * 100 if total_walls > 0 else 0
        
        # Track entity types for this wall type
        entity_types = list(set([wall.is_a() for wall in wall_list]))
        
        # Get material layer information from wall type
        material_layers = []
        total_thickness = 0
        
        # Try to get material layer information from the wall type
        sample_wall = wall_list[0]
        if hasattr(sample_wall, 'IsTypedBy') and sample_wall.IsTypedBy:
            for type_rel in sample_wall.IsTypedBy:
                if hasattr(type_rel, 'RelatingType'):
                    wall_type_obj = type_rel.RelatingType
                    
                    # Check for material associations on the type
                    for assoc in wall_type_obj.HasAssociations or []:
                        if assoc.is_a() == 'IfcRelAssociatesMaterial':
                            mat_select = assoc.RelatingMaterial
                            if mat_select.is_a() == 'IfcMaterialLayerSet':
                                # Extract material layers
                                for layer in mat_select.MaterialLayers:
                                    layer_name = 'Unnamed'
                                    if layer.Material and hasattr(layer.Material, 'Name') and layer.Material.Name:
                                        layer_name = layer.Material.Name
                                    
                                    layer_thickness = 0
                                    if hasattr(layer, 'LayerThickness'):
                                        layer_thickness = layer.LayerThickness
                                    
                                    material_layers.append({
                                        'name': layer_name,
                                        'thickness': layer_thickness
                                    })
                                    total_thickness += layer_thickness
        
        # Add to wall type counts
        wall_type_counts[wall_type_name] = {
            'count': count,
            'percentage': round(percentage, 2)
        }
        
        # Add to wall type details
        wall_type_details[wall_type_name] = {
            'count': count,
            'percentage': round(percentage, 2),
            'thickness': total_thickness if total_thickness > 0 else None,
            'material_layers': material_layers,
            'entity_types': entity_types
        }
    
    return {
        'total_walls': total_walls,
        'wall_type_counts': wall_type_counts,
        'wall_type_details': wall_type_details
    }