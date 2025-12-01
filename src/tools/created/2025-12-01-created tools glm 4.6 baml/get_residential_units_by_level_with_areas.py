import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import math
from typing import List, Dict, Any, Optional

def get_residential_units_by_level_with_areas(
    ifc_file,
    level_identifier: str,
    residential_keywords: List[str] = ['kavel', 'wohn', 'apartment', 'residential', 'unit', 'whg', 'flat', 'wohnung'],
    area_property_sets: List[str] = ['Qto_SpaceBaseQuantities', 'BaseQuantities', 'PSet_Room', 'ArchiCADQuantities', 'Dimensions'],
    area_property_names: List[str] = ['GrossFloorArea', 'NetFloorArea', 'Area', 'FloorArea', 'BruttoFläche', 'NettoFläche'],
    case_sensitive: bool = False,
    include_diagnostics: bool = False,
    placeholder_threshold: float = 1.0,
    detect_placeholders: bool = True,
    include_area_quality_analysis: bool = False,
    fallback_to_geometry: bool = False
) -> Dict[str, Any]:
    """
    Extracts residential units from a specific building level with their gross floor areas.
    
    This function handles the common BIM analysis task of finding residential units 
    (apartments, condos, housing units) on specific floors and extracting their areas,
    with robust handling of multilingual models and various property naming conventions.
    Enhanced with placeholder detection and geometric fallback capabilities.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_identifier: Level name or partial identifier (e.g., '11', 'Level 11', 'elfde verdieping')
        residential_keywords: List of keywords to identify residential units
        area_property_sets: Property sets to search for area information
        area_property_names: Property names for area data
        case_sensitive: Whether matching should be case sensitive
        include_diagnostics: Include diagnostic information about area extraction
        placeholder_threshold: Minimum area value to consider valid (to filter out placeholder values)
        detect_placeholders: Automatically detect when all areas are identical or below threshold
        include_area_quality_analysis: Provide detailed analysis of area data quality including variance analysis
        fallback_to_geometry: Attempt geometric area calculation when property-based areas are detected as placeholders
    
    Returns:
        Dict containing:
        - 'level_found': The actual level name that matched
        - 'residential_units': List of dicts with 'name', 'number', 'gross_area', 'area_source'
        - 'total_units': Count of residential units found
        - 'total_area': Sum of all gross areas
        - 'diagnostics': Optional diagnostic information
        - 'area_quality_analysis': Optional area quality analysis when enabled
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = get_residential_units_by_level_with_areas(
        ...     model, 
        ...     level_identifier='11',
        ...     include_diagnostics=True,
        ...     detect_placeholders=True,
        ...     fallback_to_geometry=True
        ... )
        >>> print(f"Found {result['total_units']} units with total area {result['total_area']} m²")
    """
    
    result = {
        'level_found': None,
        'residential_units': [],
        'total_units': 0,
        'total_area': 0.0,
        'diagnostics': [] if include_diagnostics else None,
        'area_quality_analysis': None
    }
    
    try:
        # Step 1: Find the building storey by matching level identifier
        target_storey = None
        level_identifier_cmp = level_identifier if case_sensitive else level_identifier.lower()
        
        for storey in ifc_file.by_type('IfcBuildingStorey'):
            storey_name = storey.Name or ''
            storey_name_cmp = storey_name if case_sensitive else storey_name.lower()
            
            if level_identifier_cmp in storey_name_cmp:
                target_storey = storey
                result['level_found'] = storey_name
                break
        
        if not target_storey:
            if include_diagnostics:
                result['diagnostics'].append(f"No building storey found matching '{level_identifier}'")
            return result
        
        # Step 2: Find spaces contained in this storey using spatial relationships
        spaces_in_storey = []
        
        # Method 1: Using get_decomposition (preferred)
        try:
            elements = ifcopenshell.util.element.get_decomposition(target_storey)
            spaces_in_storey = [elem for elem in elements if elem.is_a('IfcSpace')]
        except:
            # Method 2: Manual relationship traversal
            for rel in ifc_file.by_type('IfcRelContainedInSpatialStructure'):
                if rel.RelatingStructure == target_storey:
                    for element in rel.RelatedElements:
                        if element.is_a('IfcSpace'):
                            spaces_in_storey.append(element)
        
        if include_diagnostics:
            result['diagnostics'].append(f"Found {len(spaces_in_storey)} spaces in storey '{target_storey.Name}'")
        
        # Step 3: Identify residential units and extract areas
        all_area_values_for_analysis = []
        area_sources_for_analysis = []
        
        for space in spaces_in_storey:
            # Determine if this is a residential unit
            space_name = space.Name or ''
            space_longname = space.LongName or ''
            
            is_residential = False
            for keyword in residential_keywords:
                keyword_cmp = keyword if case_sensitive else keyword.lower()
                name_cmp = space_name if case_sensitive else space_name.lower()
                longname_cmp = space_longname if case_sensitive else space_longname.lower()
                
                if keyword_cmp in name_cmp or keyword_cmp in longname_cmp:
                    is_residential = True
                    break
            
            if not is_residential:
                continue
            
            # Step 4: Extract gross floor areas from various property sets
            gross_area = None
            net_area = None
            area_source = None
            all_area_values = {}
            
            # Check all property definitions
            for definition in space.IsDefinedBy:
                if hasattr(definition, 'RelatingPropertyDefinition'):
                    prop_def = definition.RelatingPropertyDefinition
                    
                    # Handle property sets
                    if prop_def.is_a('IfcPropertySet'):
                        if prop_def.Name in area_property_sets:
                            for prop in prop_def.HasProperties:
                                prop_name = prop.Name
                                
                                # Extract different types of property values
                                if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                    prop_value = prop.NominalValue.wrappedValue
                                    
                                    # Look for area-related properties
                                    prop_name_lower = prop_name.lower()
                                    if any(area_term in prop_name_lower for area_term in ['area', 'fläche', 'flaeche', 'oppervlakte']):
                                        all_area_values[f'{prop_def.Name}.{prop_name}'] = prop_value
                                        
                                        # Try to identify gross vs net area
                                        if any(gross_term in prop_name_lower for gross_term in ['gross', 'brutto', 'total', 'totaal']):
                                            gross_area = prop_value
                                            area_source = f'{prop_def.Name}.{prop_name}'
                                        elif any(net_term in prop_name_lower for net_term in ['net', 'netto']):
                                            net_area = prop_value
                                            area_source = f'{prop_def.Name}.{prop_name}'
                                
                                elif hasattr(prop, 'AreaValue'):
                                    all_area_values[f'{prop_def.Name}.{prop_name}'] = prop.AreaValue
                                    if 'gross' in prop_name.lower():
                                        gross_area = prop.AreaValue
                                        area_source = f'{prop_def.Name}.{prop_name}'
                                    elif 'net' in prop_name.lower():
                                        net_area = prop.AreaValue
                                        area_source = f'{prop_def.Name}.{prop_name}'
                    
                    # Handle quantity sets
                    elif prop_def.is_a('IfcElementQuantity'):
                        if prop_def.Name in area_property_sets:
                            for quant in prop_def.Quantities:
                                quant_name = quant.Name
                                
                                if hasattr(quant, 'AreaValue'):
                                    all_area_values[f'{prop_def.Name}.{quant_name}'] = quant.AreaValue
                                    
                                    # Identify gross vs net area
                                    quant_name_lower = quant_name.lower()
                                    if any(gross_term in quant_name_lower for gross_term in ['gross', 'brutto', 'total', 'totaal']):
                                        gross_area = quant.AreaValue
                                        area_source = f'{prop_def.Name}.{quant_name}'
                                    elif any(net_term in quant_name_lower for net_term in ['net', 'netto']):
                                        net_area = quant.AreaValue
                                        area_source = f'{prop_def.Name}.{quant_name}'
            
            # Use gross area if available, otherwise net area
            final_area = gross_area if gross_area is not None else net_area
            
            # If still no area found, look for any area value in all_area_values
            if final_area is None and all_area_values:
                # Use the first area value found as a fallback
                final_area = list(all_area_values.values())[0]
                area_source = list(all_area_values.keys())[0]
            
            # Store for quality analysis
            if final_area is not None:
                all_area_values_for_analysis.append(final_area)
                if area_source:
                    area_sources_for_analysis.append(area_source)
            
            # Filter out placeholder values
            if final_area is not None and final_area < placeholder_threshold:
                if include_diagnostics:
                    result['diagnostics'].append(f"Space '{space_name}' area {final_area} below threshold {placeholder_threshold}, treating as missing")
                final_area = None
                area_source = None
            
            # Store residential unit information
            unit_info = {
                'name': space_name,
                'number': space_name,  # Using Name as number since it typically contains unit number
                'gross_area': final_area,
                'area_source': area_source
            }
            
            result['residential_units'].append(unit_info)
            
            if include_diagnostics:
                result['diagnostics'].append(f"Processed space '{space_name}': area={final_area}, source={area_source}")
        
        # Step 5: Area quality analysis and placeholder detection
        if include_area_quality_analysis or detect_placeholders:
            quality_analysis = {
                'total_areas_found': len(all_area_values_for_analysis),
                'area_values': all_area_values_for_analysis.copy(),
                'area_sources': list(set(area_sources_for_analysis)),
                'unique_sources': len(set(area_sources_for_analysis))
            }
            
            if all_area_values_for_analysis:
                quality_analysis['min_area'] = min(all_area_values_for_analysis)
                quality_analysis['max_area'] = max(all_area_values_for_analysis)
                quality_analysis['mean_area'] = sum(all_area_values_for_analysis) / len(all_area_values_for_analysis)
                quality_analysis['variance'] = sum((x - quality_analysis['mean_area'])**2 for x in all_area_values_for_analysis) / len(all_area_values_for_analysis)
                quality_analysis['std_dev'] = math.sqrt(quality_analysis['variance'])
                
                # Detect if all areas are identical (potential placeholders)
                unique_areas = set(all_area_values_for_analysis)
                quality_analysis['unique_area_count'] = len(unique_areas)
                quality_analysis['all_areas_identical'] = len(unique_areas) == 1
                
                # Check if areas are below threshold
                quality_analysis['all_areas_below_threshold'] = all(area < placeholder_threshold for area in all_area_values_for_analysis)
                
                # Determine if placeholder detection is triggered
                is_placeholder_data = False
                if detect_placeholders:
                    if quality_analysis['all_areas_identical']:
                        is_placeholder_data = True
                        if include_diagnostics:
                            result['diagnostics'].append(f"Placeholder detected: All {len(all_area_values_for_analysis)} areas are identical ({list(unique_areas)[0]})")
                    elif quality_analysis['all_areas_below_threshold']:
                        is_placeholder_data = True
                        if include_diagnostics:
                            result['diagnostics'].append(f"Placeholder detected: All {len(all_area_values_for_analysis)} areas are below threshold {placeholder_threshold}")
                    elif quality_analysis['std_dev'] < 0.1:  # Very low variance
                        is_placeholder_data = True
                        if include_diagnostics:
                            result['diagnostics'].append(f"Placeholder detected: Very low variance ({quality_analysis['std_dev']:.3f}) suggests placeholder data")
                
                quality_analysis['is_placeholder_data'] = is_placeholder_data
                
                # Step 6: Fallback to geometry if placeholder detected and fallback enabled
                if is_placeholder_data and fallback_to_geometry:
                    if include_diagnostics:
                        result['diagnostics'].append("Attempting geometric area calculation as fallback")
                    
                    # Set up geometry settings
                    settings = ifcopenshell.geom.settings()
                    settings.set(settings.USE_WORLD_COORDS, True)
                    
                    for i, unit_info in enumerate(result['residential_units']):
                        if unit_info['gross_area'] is not None:  # Only recalculate those with placeholder areas
                            # Find the corresponding space
                            space = None
                            for s in spaces_in_storey:
                                if s.Name == unit_info['name']:
                                    space = s
                                    break
                            
                            if space:
                                try:
                                    # Get geometry for the space
                                    shape = ifcopenshell.geom.create_shape(settings, space)
                                    geometry = shape.geometry
                                    
                                    # Calculate area from geometry
                                    area = 0.0
                                    
                                    # Get vertices and faces
                                    verts = geometry.verts
                                    faces = geometry.faces
                                    
                                    # Calculate area from triangular faces
                                    for i in range(0, len(faces), 3):
                                        if i + 2 < len(faces):
                                            # Get the three vertex indices for this triangle
                                            idx1 = faces[i] * 3
                                            idx2 = faces[i + 1] * 3
                                            idx3 = faces[i + 2] * 3
                                            
                                            if idx1 + 2 < len(verts) and idx2 + 2 < len(verts) and idx3 + 2 < len(verts):
                                                # Get the three vertices
                                                v1 = [verts[idx1], verts[idx1 + 1], verts[idx1 + 2]]
                                                v2 = [verts[idx2], verts[idx2 + 1], verts[idx2 + 2]]
                                                v3 = [verts[idx3], verts[idx3 + 1], verts[idx3 + 2]]
                                                
                                                # Calculate triangle area using cross product
                                                vec1 = [v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]]
                                                vec2 = [v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]]
                                                
                                                # Cross product
                                                cross = [
                                                    vec1[1] * vec2[2] - vec1[2] * vec2[1],
                                                    vec1[2] * vec2[0] - vec1[0] * vec2[2],
                                                    vec1[0] * vec2[1] - vec1[1] * vec2[0]
                                                ]
                                                
                                                # Magnitude of cross product gives 2x triangle area
                                                triangle_area = math.sqrt(cross[0]**2 + cross[1]**2 + cross[2]**2) / 2
                                                area += triangle_area
                                    
                                    # Update the unit info with geometric area
                                    unit_info['gross_area'] = round(area, 1)
                                    unit_info['area_source'] = 'geometric_calculation'
                                    
                                    if include_diagnostics:
                                        result['diagnostics'].append(f"Geometric calculation for '{unit_info['name']}': {area:.1f} m²")
                                    
                                except Exception as e:
                                    if include_diagnostics:
                                        result['diagnostics'].append(f"Geometric calculation failed for '{unit_info['name']}': {str(e)}")
            
            if include_area_quality_analysis:
                result['area_quality_analysis'] = quality_analysis
        
        # Calculate totals
        result['total_units'] = len(result['residential_units'])
        result['total_area'] = sum(unit['gross_area'] for unit in result['residential_units'] if unit['gross_area'] is not None)
        
    except Exception as e:
        if include_diagnostics:
            result['diagnostics'].append(f"Error during processing: {str(e)}")
    
    return result