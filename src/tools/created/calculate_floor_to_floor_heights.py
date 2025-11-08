import ifcopenshell
import ifcopenshell.util.placement
from typing import List, Dict, Any, Optional

def calculate_floor_to_floor_heights(
    ifc_file: ifcopenshell.file,
    include_level_details: bool = True,
    sort_by_elevation: bool = True,
    height_unit: str = 'm',
    include_summary: bool = True
) -> Dict[str, Any]:
    """
    Calculates floor-to-floor heights for building levels by analyzing elevation differences between consecutive levels.
    This function builds on building level extraction to provide comprehensive vertical building analysis,
    including individual floor heights, total building height, and height consistency analysis.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        include_level_details: Boolean to include full level information (default: True)
        sort_by_elevation: Boolean to sort levels by elevation (default: True)
        height_unit: Unit for height output ('m', 'mm', 'ft', default: 'm')
        include_summary: Boolean to include height statistics (default: True)
    
    Returns:
        Dict containing:
        - levels: List of level information with elevations and floor-to-floor heights
        - floor_heights: List of floor-to-floor heights between consecutive levels
        - total_height: Total building height from lowest to highest level
        - height_statistics: Dict with min, max, average floor heights (if include_summary=True)
        - height_consistency: Analysis of height consistency across the building
    
    Example usage:
        import ifcopenshell
        model = ifcopenshell.open('building.ifc')
        result = calculate_floor_to_floor_heights(model, height_unit='m')
        print(f"Total building height: {result['total_height']}m")
        print(f"Average floor height: {result['height_statistics']['average']}m")
    """
    try:
        # Validate input parameters
        if not isinstance(ifc_file, ifcopenshell.file):
            raise ValueError("ifc_file must be a valid ifcopenshell.file object")
        
        if height_unit not in ['m', 'mm', 'ft']:
            raise ValueError("height_unit must be one of: 'm', 'mm', 'ft'")
        
        # Extract building storeys
        storeys = ifc_file.by_type('IfcBuildingStorey')
        if not storeys:
            raise ValueError("No IfcBuildingStorey entities found in the IFC model")
        
        # Extract level information
        levels = []
        for storey in storeys:
            name = storey.Name if storey.Name else 'Unnamed'
            
            # Get elevation from placement matrix
            if storey.ObjectPlacement:
                matrix = ifcopenshell.util.placement.get_local_placement(storey.ObjectPlacement)
                elevation_mm = matrix[2, 3]  # Z coordinate in millimeters
            else:
                elevation_mm = 0.0
            
            level_info = {
                'name': name,
                'elevation_mm': elevation_mm,
                'storey_id': storey.id()
            }
            
            if include_level_details:
                level_info.update({
                    'storey': storey,
                    'long_name': getattr(storey, 'LongName', None),
                    'description': getattr(storey, 'Description', None)
                })
            
            levels.append(level_info)
        
        # Sort levels by elevation if requested
        if sort_by_elevation:
            levels.sort(key=lambda x: x['elevation_mm'])
        
        # Convert elevations to requested unit
        unit_conversion = {
            'm': 0.001,
            'mm': 1.0,
            'ft': 0.001 / 0.3048  # mm to feet
        }
        conversion_factor = unit_conversion[height_unit]
        
        for level in levels:
            level['elevation'] = level['elevation_mm'] * conversion_factor
        
        # Calculate floor-to-floor heights
        floor_heights = []
        for i in range(1, len(levels)):
            prev_elevation = levels[i-1]['elevation_mm']
            curr_elevation = levels[i]['elevation_mm']
            height_mm = curr_elevation - prev_elevation
            height_converted = height_mm * conversion_factor
            
            floor_height_info = {
                'from_level': levels[i-1]['name'],
                'to_level': levels[i]['name'],
                'height_mm': height_mm,
                'height': height_converted
            }
            
            floor_heights.append(floor_height_info)
            
            # Add floor-to-floor height to the upper level
            levels[i]['floor_to_floor_height'] = height_converted
            levels[i]['floor_to_floor_height_mm'] = height_mm
        
        # Calculate total building height
        if len(levels) >= 2:
            total_height_mm = levels[-1]['elevation_mm'] - levels[0]['elevation_mm']
            total_height = total_height_mm * conversion_factor
        else:
            total_height_mm = 0.0
            total_height = 0.0
        
        # Prepare result
        result = {
            'levels': levels,
            'floor_heights': floor_heights,
            'total_height_mm': total_height_mm,
            'total_height': total_height,
            'unit': height_unit
        }
        
        # Add height statistics if requested
        if include_summary and floor_heights:
            heights_mm = [fh['height_mm'] for fh in floor_heights]
            height_statistics = {
                'min_mm': min(heights_mm),
                'max_mm': max(heights_mm),
                'average_mm': sum(heights_mm) / len(heights_mm),
                'min': min(heights_mm) * conversion_factor,
                'max': max(heights_mm) * conversion_factor,
                'average': sum(heights_mm) / len(heights_mm) * conversion_factor,
                'count': len(heights_mm)
            }
            
            # Analyze height consistency
            unique_heights = set(round(h, 3) for h in heights_mm)
            height_consistency = {
                'is_consistent': len(unique_heights) == 1,
                'unique_heights_count': len(unique_heights),
                'most_common_height_mm': max(set(heights_mm), key=heights_mm.count),
                'most_common_height': max(set(heights_mm), key=heights_mm.count) * conversion_factor,
                'variation_range_mm': max(heights_mm) - min(heights_mm),
                'variation_range': (max(heights_mm) - min(heights_mm)) * conversion_factor
            }
            
            result['height_statistics'] = height_statistics
            result['height_consistency'] = height_consistency
        
        return result
        
    except Exception as e:
        raise RuntimeError(f"Error calculating floor-to-floor heights: {str(e)}")