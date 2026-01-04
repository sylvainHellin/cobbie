import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional, Union, Any

def extract_building_storey_heights(
    ifc_file: ifcopenshell.file,
    storey_names: Optional[List[str]] = None,
    calculate_heights: bool = True,
    sort_by_elevation: bool = True,
    include_properties: bool = False,
    return_format: str = 'summary'
) -> Dict[str, Any]:
    """
    Extracts building storey elevation information and calculates floor-to-floor heights.
    
    This function handles the common BIM analysis task of understanding vertical 
    relationships between building levels by retrieving IfcBuildingStorey elements 
    and their elevation properties.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        storey_names: Optional list of specific storey names to analyze (if None, analyzes all storeys)
        calculate_heights: Whether to calculate floor-to-floor heights between consecutive storeys (default True)
        sort_by_elevation: Whether to sort storeys by elevation before calculating heights (default True)
        include_properties: Whether to include additional storey properties beyond elevation (default False)
        return_format: Format of return data - 'summary' for basic info, 'detailed' for all properties, 
                      'heights_only' for just height calculations (default 'summary')
    
    Returns:
        Dict containing storey information and calculated heights.
        Example: {'storeys': [{'name': 'First Floor', 'elevation': 0.0}, {'name': 'Second Floor', 'elevation': 4.57}], 
                 'floor_to_floor_heights': {'First Floor to Second Floor': 4.57}}
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = extract_building_storey_heights(model)
        >>> print(result['floor_to_floor_heights'])
    """
    
    try:
        # Validate input parameters
        if not isinstance(ifc_file, ifcopenshell.file):
            raise ValueError("ifc_file must be a valid ifcopenshell.file object")
        
        if return_format not in ['summary', 'detailed', 'heights_only']:
            raise ValueError("return_format must be one of: 'summary', 'detailed', 'heights_only'")
        
        # Get all building storeys
        all_storeys = ifc_file.by_type('IfcBuildingStorey')
        
        if not all_storeys:
            return {
                'storeys': [],
                'floor_to_floor_heights': {},
                'error': 'No IfcBuildingStorey elements found in the model'
            }
        
        # Filter storeys if specific names provided
        if storey_names:
            filtered_storeys = []
            for storey in all_storeys:
                storey_name = storey.Name if storey.Name else 'Unnamed'
                if storey_name in storey_names:
                    filtered_storeys.append(storey)
            storeys_to_process = filtered_storeys
        else:
            storeys_to_process = all_storeys
        
        # Extract storey information
        storey_data = []
        for storey in storeys_to_process:
            name = storey.Name if storey.Name else 'Unnamed'
            elevation = storey.Elevation if storey.Elevation is not None else None
            
            storey_info = {
                'name': name,
                'elevation': elevation
            }
            
            # Include additional properties if requested
            if include_properties or return_format == 'detailed':
                try:
                    psets = ifcopenshell.util.element.get_psets(storey)
                    storey_info['properties'] = psets
                except Exception as e:
                    storey_info['properties'] = {'error': str(e)}
            
            storey_data.append(storey_info)
        
        # Sort by elevation if requested
        if sort_by_elevation:
            storey_data.sort(key=lambda x: x['elevation'] if x['elevation'] is not None else float('-inf'))
        
        # Calculate floor-to-floor heights
        floor_to_floor_heights = {}
        if calculate_heights and len(storey_data) > 1:
            for i in range(len(storey_data) - 1):
                current_storey = storey_data[i]
                next_storey = storey_data[i + 1]
                
                if (current_storey['elevation'] is not None and 
                    next_storey['elevation'] is not None):
                    height = next_storey['elevation'] - current_storey['elevation']
                    height_key = f"{current_storey['name']} to {next_storey['name']}"
                    floor_to_floor_heights[height_key] = height
        
        # Format return data based on return_format
        if return_format == 'heights_only':
            return {
                'floor_to_floor_heights': floor_to_floor_heights
            }
        elif return_format == 'detailed':
            return {
                'storeys': storey_data,
                'floor_to_floor_heights': floor_to_floor_heights,
                'total_storeys': len(storey_data)
            }
        else:  # summary
            # For summary, only include basic info
            summary_storeys = []
            for storey in storey_data:
                summary_storeys.append({
                    'name': storey['name'],
                    'elevation': storey['elevation']
                })
            
            return {
                'storeys': summary_storeys,
                'floor_to_floor_heights': floor_to_floor_heights
            }
    
    except Exception as e:
        return {
            'storeys': [],
            'floor_to_floor_heights': {},
            'error': f'Error processing storey data: {str(e)}'
        }