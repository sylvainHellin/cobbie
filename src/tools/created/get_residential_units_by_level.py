import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union


def get_residential_units_by_level(
    ifc_file,
    level_name: str,
    residential_keywords: List[str] = None,
    area_sources: List[str] = None,
    price_per_unit: Optional[float] = None,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Extracts residential units from a specific building level with comprehensive area analysis.
    
    This function identifies residential units through semantic analysis of names, object types,
    and property values, then provides detailed area information including gross floor area,
    net area, and calculated areas from pricing data when standard quantities are unavailable.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_name: Name of the building level to search (e.g., '10 tiende verdieping', 'Ground Floor')
        residential_keywords: List of keywords to identify residential units
            (default: ['woning', 'appartement', 'unit', 'residential', 'woon', 'flat', 'kavel'])
        area_sources: Priority order for area extraction
            (default: ['quantities', 'properties', 'calculated'])
        price_per_unit: Price per unit for area calculation fallback
            (default: None, auto-detects from properties)
        include_details: Include full property analysis (default: False)
    
    Returns:
        Dict containing:
        - level_info: Information about the searched level
        - residential_units: List of residential units with area data
        - total_units: Count of residential units found
        - area_summary: Statistics about unit areas
        - data_quality: Assessment of area data completeness
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = get_residential_units_by_level(
        ...     model, 
        ...     '10 tiende verdieping',
        ...     include_details=True
        ... )
        >>> print(f"Found {result['total_units']} residential units")
    """
    # Set default values
    if residential_keywords is None:
        residential_keywords = ['woning', 'appartement', 'unit', 'residential', 'woon', 'flat', 'kavel']
    if area_sources is None:
        area_sources = ['quantities', 'properties', 'calculated']
    
    # Initialize result structure
    result = {
        'level_info': {'name': level_name, 'found': False, 'elevation': None},
        'residential_units': [],
        'total_units': 0,
        'area_summary': {'total_area': 0, 'average_area': 0, 'min_area': None, 'max_area': None},
        'data_quality': {'complete_areas': 0, 'placeholder_areas': 0, 'missing_areas': 0}
    }
    
    try:
        # Find the target building storey
        target_level = None
        storeys = ifc_file.by_type('IfcBuildingStorey')
        
        for storey in storeys:
            if level_name.lower() in storey.Name.lower() or storey.Name.lower() in level_name.lower():
                target_level = storey
                result['level_info']['found'] = True
                result['level_info']['name'] = storey.Name
                # Try to get elevation
                if hasattr(storey, 'Elevation'):
                    result['level_info']['elevation'] = storey.Elevation
                break
        
        if not target_level:
            return result
        
        # Get all elements on this level
        elements = ifcopenshell.util.element.get_decomposition(target_level)
        
        # Filter for spaces (residential units are typically represented as IfcSpace)
        spaces = [elem for elem in elements if elem.is_a('IfcSpace')]
        
        # Process each space to identify residential units and extract area data
        for space in spaces:
            unit_info = {
                'id': space.id,
                'name': getattr(space, 'Name', None) or 'N/A',
                'long_name': getattr(space, 'LongName', None) or 'N/A',
                'object_type': space.is_a(),
                'areas': {},
                'properties': {},
                'is_residential': False,
                'identification_method': None
            }
            
            # Check if this is a residential unit
            space_name = (unit_info['name'] or '').lower()
            space_long_name = (unit_info['long_name'] or '').lower()
            
            # Method 1: Check name/long_name for residential keywords
            if any(keyword in space_name or keyword in space_long_name 
                   for keyword in residential_keywords):
                unit_info['is_residential'] = True
                unit_info['identification_method'] = 'name_keywords'
            
            # Method 2: Check property sets for residential indicators
            if not unit_info['is_residential']:
                try:
                    psets = ifcopenshell.util.element.get_psets(space)
                    for pset_name, pset_data in psets.items():
                        if isinstance(pset_data, dict):
                            for prop_name, prop_value in pset_data.items():
                                if isinstance(prop_value, str):
                                    prop_value_lower = prop_value.lower()
                                    if any(keyword in prop_value_lower for keyword in residential_keywords):
                                        unit_info['is_residential'] = True
                                        unit_info['identification_method'] = 'property_keywords'
                                        break
                        if unit_info['is_residential']:
                            break
                except Exception:
                    pass  # Continue if property extraction fails
            
            # Method 3: Check if name follows residential unit pattern (e.g., 10.01, A-101, etc.)
            if not unit_info['is_residential']:
                import re
                # Pattern: floor.unit (e.g., 10.01, 12.03)
                if re.match(r'^\d+\.\d+$', unit_info['name']):
                    unit_info['is_residential'] = True
                    unit_info['identification_method'] = 'naming_pattern'
            
            # If identified as residential, extract area information
            if unit_info['is_residential']:
                # Extract area data from multiple sources
                detected_price_per_unit = None
                
                try:
                    # Get all property sets and quantities
                    psets = ifcopenshell.util.element.get_psets(space)
                    
                    for source in area_sources:
                        if source == 'quantities':
                            # Extract from quantities
                            qtos = ifcopenshell.util.element.get_psets(space, qtos_only=True)
                            for qto_name, qto_data in qtos.items():
                                if isinstance(qto_data, dict):
                                    for prop_name, prop_value in qto_data.items():
                                        if 'area' in prop_name.lower() or 'oppervlak' in prop_name.lower():
                                            if isinstance(prop_value, (int, float)) and prop_value > 0:
                                                unit_info['areas'][f'quantity_{prop_name}'] = prop_value
                        
                        elif source == 'properties':
                            # Extract from properties
                            psets_props = ifcopenshell.util.element.get_psets(space, psets_only=True)
                            for pset_name, pset_data in psets_props.items():
                                if isinstance(pset_data, dict):
                                    for prop_name, prop_value in pset_data.items():
                                        # Look for area-related properties
                                        if any(keyword in prop_name.lower() for keyword in 
                                              ['oppervlak', 'area', 'vlak', 'prijs']):
                                            if isinstance(prop_value, (int, float)):
                                                if 'prijs' in prop_name.lower():
                                                    # This might be price calculation
                                                    if 'x oppervlakte' in prop_name.lower():
                                                        unit_info['areas']['calculated_from_price'] = prop_value
                                                    elif 'prijs/m2' in prop_name.lower() or 'prijs per' in prop_name.lower():
                                                        detected_price_per_unit = prop_value
                                                else:
                                                    unit_info['areas'][f'property_{prop_name}'] = prop_value
                        
                        elif source == 'calculated':
                            # Calculate from price data if available
                            if 'calculated_from_price' in unit_info['areas']:
                                price_total = unit_info['areas']['calculated_from_price']
                                price_unit = price_per_unit or detected_price_per_unit
                                
                                if price_unit and price_unit > 0:
                                    calculated_area = price_total / price_unit
                                    unit_info['areas']['calculated_area'] = calculated_area
                
                except Exception as e:
                    # Continue even if area extraction fails
                    pass
                
                # Determine the best area value
                best_area = None
                area_source_used = None
                
                # Priority order for area selection
                area_priority = [
                    'GrossFloorArea', 'gross_floor_area', 'quantity_GrossFloorArea',
                    'Area', 'area', 'quantity_Area',
                    'calculated_area'
                ]
                
                for area_key in area_priority:
                    if area_key in unit_info['areas']:
                        area_value = unit_info['areas'][area_key]
                        if isinstance(area_value, (int, float)) and area_value > 1.0:  # Filter out placeholder 1.0
                            best_area = area_value
                            area_source_used = area_key
                            break
                
                # If no valid area found, check if we have any area at all
                if best_area is None and unit_info['areas']:
                    for area_key, area_value in unit_info['areas'].items():
                        if isinstance(area_value, (int, float)) and area_value > 0:
                            best_area = area_value
                            area_source_used = area_key
                            break
                
                unit_info['best_area'] = best_area
                unit_info['area_source'] = area_source_used
                
                # Assess data quality
                if best_area is None:
                    result['data_quality']['missing_areas'] += 1
                elif best_area == 1.0:  # Likely placeholder
                    result['data_quality']['placeholder_areas'] += 1
                else:
                    result['data_quality']['complete_areas'] += 1
                
                # Include detailed properties if requested
                if include_details:
                    try:
                        unit_info['all_properties'] = ifcopenshell.util.element.get_psets(space)
                    except Exception:
                        unit_info['all_properties'] = {}
                
                result['residential_units'].append(unit_info)
        
        # Calculate summary statistics
        result['total_units'] = len(result['residential_units'])
        
        if result['residential_units']:
            valid_areas = [unit['best_area'] for unit in result['residential_units'] 
                          if unit['best_area'] is not None and unit['best_area'] > 1.0]
            
            if valid_areas:
                result['area_summary']['total_area'] = sum(valid_areas)
                result['area_summary']['average_area'] = sum(valid_areas) / len(valid_areas)
                result['area_summary']['min_area'] = min(valid_areas)
                result['area_summary']['max_area'] = max(valid_areas)
            else:
                # Include placeholder areas in summary if no valid areas found
                all_areas = [unit['best_area'] for unit in result['residential_units'] 
                            if unit['best_area'] is not None]
                if all_areas:
                    result['area_summary']['total_area'] = sum(all_areas)
                    result['area_summary']['average_area'] = sum(all_areas) / len(all_areas)
                    result['area_summary']['min_area'] = min(all_areas)
                    result['area_summary']['max_area'] = max(all_areas)
    
    except Exception as e:
        # Add error information to result
        result['error'] = str(e)
    
    return result