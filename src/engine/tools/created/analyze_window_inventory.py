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


def analyze_window_inventory(model_path: str) -> Dict[str, Any]:
    """
    Analyze all windows in an IFC model and provide comprehensive inventory including types, dimensions, and quantities.
    
    This function extracts all IfcWindow entities and analyzes their dimensional properties,
    grouping them by type, size, and floor organization. It uses multiple sources of dimensional
    data including direct attributes and property sets to ensure comprehensive analysis.
    
    Args:
        model_path (str): Path to the IFC model file
        
    Returns:
        Dict containing:
        - total_windows: Total count of windows
        - window_types: Dictionary mapping window types to their details
        - size_distribution: Breakdown of windows by dimensions
        - floor_distribution: Windows organized by floor with type information
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all window entities
    windows = model.by_type('IfcWindow')
    total_windows = len(windows)
    
    # Initialize data structures
    window_types = {}
    size_distribution = {}
    floor_distribution = {}
    window_details = []
    
    # Process each window
    for window in windows:
        # Extract basic information
        window_info = {
            'id': window.GlobalId,
            'name': window.Name,
            'object_type': window.ObjectType
        }
        
        # Extract dimensions from multiple sources
        width = None
        height = None
        area = None
        volume = None
        
        # Try direct attributes first
        if hasattr(window, 'OverallWidth') and window.OverallWidth is not None:
            width = float(window.OverallWidth)
        if hasattr(window, 'OverallHeight') and window.OverallHeight is not None:
            height = float(window.OverallHeight)
        
        # Extract from property sets
        psets = ifcopenshell.util.element.get_psets(window)
        
        # Check BaseQuantities for dimensional data
        if 'BaseQuantities' in psets:
            base_quantities = psets['BaseQuantities']
            if width is None and 'Width' in base_quantities:
                width = float(base_quantities['Width'])
            if height is None and 'Height' in base_quantities:
                height = float(base_quantities['Height'])
            if 'Area' in base_quantities:
                area = float(base_quantities['Area'])
            if 'GrossArea' in base_quantities:
                gross_area = float(base_quantities['GrossArea'])
                area = gross_area if area is None else area
            if 'Volume' in base_quantities:
                volume = float(base_quantities['Volume'])
        
        # Store dimensions
        window_info['width'] = width
        window_info['height'] = height
        window_info['area'] = area
        window_info['volume'] = volume
        
        # Calculate size key for grouping (rounded to 2 decimal places)
        if width is not None and height is not None:
            size_key = f"{width:.2f}m × {height:.2f}m"
        else:
            size_key = "Unknown dimensions"
        
        window_info['size_key'] = size_key
        
        # Extract type information
        type_name = "Unknown Type"
        if window.IsDefinedBy:
            for rel in window.IsDefinedBy:
                if hasattr(rel, 'RelatingType') and rel.RelatingType:
                    type_name = rel.RelatingType.Name or "Unnamed Type"
                    window_info['type_id'] = rel.RelatingType.GlobalId
                    break
        
        window_info['type_name'] = type_name
        
        # Extract floor information from name or spatial structure
        floor_name = "Unknown Floor"
        if window.Name:
            # Try to extract floor from name pattern (e.g., "Keller-Fenster-XX-X")
            name_parts = window.Name.split('-')
            if len(name_parts) >= 1:
                floor_name = name_parts[0]
        
        # Try to get floor from spatial structure
        try:
            container = ifcopenshell.util.element.get_container(window)
            if container and hasattr(container, 'Name'):
                if container.is_a('IfcBuildingStorey'):
                    floor_name = container.Name or floor_name
                elif container.is_a('IfcSpace'):
                    # Get the building storey that contains this space
                    space_container = ifcopenshell.util.element.get_container(container)
                    if space_container and space_container.is_a('IfcBuildingStorey'):
                        floor_name = space_container.Name or floor_name
        except:
            pass  # Use the name-based floor extraction
        
        window_info['floor'] = floor_name
        
        # Extract additional properties
        additional_props = {}
        for pset_name, pset_data in psets.items():
            if pset_name not in ['BaseQuantities']:  # Already processed
                for prop_name, prop_value in pset_data.items():
                    if prop_name not in ['id']:  # Skip internal IDs
                        additional_props[f"{pset_name}_{prop_name}"] = prop_value
        
        window_info['additional_properties'] = additional_props
        
        # Add to details list
        window_details.append(window_info)
        
        # Update window types grouping
        if type_name not in window_types:
            window_types[type_name] = {
                'count': 0,
                'sizes': {},
                'total_area': 0.0,
                'total_volume': 0.0,
                'windows': []
            }
        
        window_types[type_name]['count'] += 1
        window_types[type_name]['windows'].append(window_info['id'])
        
        if size_key not in window_types[type_name]['sizes']:
            window_types[type_name]['sizes'][size_key] = 0
        window_types[type_name]['sizes'][size_key] += 1
        
        if area is not None:
            window_types[type_name]['total_area'] += area
        if volume is not None:
            window_types[type_name]['total_volume'] += volume
        
        # Update size distribution
        if size_key not in size_distribution:
            size_distribution[size_key] = {
                'count': 0,
                'width': width,
                'height': height,
                'area': width * height if width and height else None,
                'types': set()
            }
        
        size_distribution[size_key]['count'] += 1
        size_distribution[size_key]['types'].add(type_name)
        
        # Update floor distribution
        if floor_name not in floor_distribution:
            floor_distribution[floor_name] = {
                'count': 0,
                'types': {},
                'sizes': {},
                'total_area': 0.0,
                'windows': []
            }
        
        floor_distribution[floor_name]['count'] += 1
        floor_distribution[floor_name]['windows'].append(window_info['id'])
        
        if type_name not in floor_distribution[floor_name]['types']:
            floor_distribution[floor_name]['types'][type_name] = 0
        floor_distribution[floor_name]['types'][type_name] += 1
        
        if size_key not in floor_distribution[floor_name]['sizes']:
            floor_distribution[floor_name]['sizes'][size_key] = 0
        floor_distribution[floor_name]['sizes'][size_key] += 1
        
        if area is not None:
            floor_distribution[floor_name]['total_area'] += area
    
    # Convert sets to lists for JSON serialization
    for size_key in size_distribution:
        size_distribution[size_key]['types'] = list(size_distribution[size_key]['types'])
    
    # Calculate summary statistics
    total_area = sum(w['area'] for w in window_details if w['area'] is not None)
    total_volume = sum(w['volume'] for w in window_details if w['volume'] is not None)
    
    # Find most common window types and sizes
    most_common_type = max(window_types.items(), key=lambda x: x[1]['count']) if window_types else None
    most_common_size = max(size_distribution.items(), key=lambda x: x[1]['count']) if size_distribution else None
    
    # Prepare final result
    result = {
        'total_windows': total_windows,
        'total_area': total_area,
        'total_volume': total_volume,
        'window_types': window_types,
        'size_distribution': size_distribution,
        'floor_distribution': floor_distribution,
        'summary': {
            'unique_types': len(window_types),
            'unique_sizes': len(size_distribution),
            'unique_floors': len(floor_distribution),
            'most_common_type': most_common_type[0] if most_common_type else None,
            'most_common_size': most_common_size[0] if most_common_size else None,
            'average_window_area': total_area / total_windows if total_windows > 0 and total_area > 0 else 0
        },
        'detailed_windows': window_details
    }
    
    return result