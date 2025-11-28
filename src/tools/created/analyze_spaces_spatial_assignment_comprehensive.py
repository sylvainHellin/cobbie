import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional, Union, Any

def analyze_spaces_spatial_assignment_comprehensive(
    ifc_file: ifcopenshell.file,
    target_level: Optional[str] = None,
    spatial_relationship_types: List[str] = ['Decomposes', 'IfcRelContainedInSpatialStructure'],
    level_property_sets: List[str] = ['Pset_SpaceCustom', 'Abhängigkeiten', 'Pset_SpaceCommon', 'Constraints'],
    level_property_names: List[str] = ['Ebene', 'Level', 'Storey', 'BuildingStorey'],
    area_property_sets: List[str] = ['Qto_SpaceBaseQuantities', 'Dimensions', 'BaseQuantities', 'Pset_SpaceCustom', 'PSet_Room'],
    area_property_names: List[str] = ['GrossFloorArea', 'NetFloorArea', 'Area', 'FloorArea'],
    include_unassigned: bool = True,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Comprehensively analyzes spatial assignment of spaces in IFC models, handling incomplete spatial relationships and providing detailed diagnostics.
    
    This function implements a multi-strategy approach:
    1) Primary spatial relationship analysis through Decomposes and IfcRelContainedInSpatialStructure
    2) Fallback property-based level assignment with flexible property set/name matching
    3) Comprehensive area extraction from multiple sources
    4) Detailed reporting of assignment completeness and data quality issues
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        target_level: Optional specific level to analyze (e.g., '4th Floor'). If None, analyzes all levels
        spatial_relationship_types: List of relationship types to check
        level_property_sets: List of property sets to search for level info
        level_property_names: List of property names to search for level info
        area_property_sets: List of property sets for area extraction
        area_property_names: List of property names for area extraction
        include_unassigned: Boolean to include spaces with no level assignment
        case_sensitive: Boolean for case-sensitive property matching
    
    Returns:
        Dict containing:
        - 'target_level_spaces': List of spaces on target level with areas
        - 'all_levels_summary': Dict mapping level names to space counts
        - 'unassigned_spaces': List of spaces with no level assignment
        - 'assignment_completeness': Percentage of spaces with level assignments
        - 'diagnostics': Details about which assignment methods succeeded
        - 'total_spaces': Total number of spaces in model
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = analyze_spaces_spatial_assignment_comprehensive(
        ...     ifc_file, target_level='4th Floor'
        ... )
        >>> print(f"Spaces on 4th Floor: {len(result['target_level_spaces'])}")
    """
    
    try:
        # Initialize result structure
        result = {
            'target_level_spaces': [],
            'all_levels_summary': {},
            'unassigned_spaces': [],
            'assignment_completeness': 0.0,
            'diagnostics': {
                'spatial_method_success': 0,
                'property_method_success': 0,
                'area_extraction_success': 0,
                'total_spaces_processed': 0
            },
            'total_spaces': 0
        }
        
        # Get all spaces
        all_spaces = ifc_file.by_type('IfcSpace')
        result['total_spaces'] = len(all_spaces)
        result['diagnostics']['total_spaces_processed'] = len(all_spaces)
        
        if not all_spaces:
            return result
        
        # Process each space
        spaces_by_level = {}
        unassigned_spaces = []
        
        for space in all_spaces:
            space_info = {
                'id': space.id(),
                'name': space.Name or space.LongName or f'Space_{space.id()}',
                'area': None,
                'level_assignment_method': None,
                'area_extraction_method': None
            }
            
            # Strategy 1: Primary spatial relationship analysis
            assigned_level = None
            assignment_method = None
            
            try:
                # Use get_container utility (most reliable method)
                container = ifcopenshell.util.element.get_container(space)
                if container and container.is_a('IfcBuildingStorey'):
                    assigned_level = container.Name
                    assignment_method = 'spatial_container'
                    result['diagnostics']['spatial_method_success'] += 1
            except:
                pass
            
            # Fallback: Check Decomposes relationship
            if not assigned_level and space.Decomposes:
                for decomposes in space.Decomposes:
                    if decomposes.is_a('IfcRelAggregates') and decomposes.RelatingObject:
                        relating_obj = decomposes.RelatingObject
                        if relating_obj.is_a('IfcBuildingStorey'):
                            assigned_level = relating_obj.Name
                            assignment_method = 'decomposes'
                            result['diagnostics']['spatial_method_success'] += 1
                            break
            
            # Fallback: Check IfcRelContainedInSpatialStructure
            if not assigned_level:
                for rel in ifc_file.get_inverse(space):
                    if rel.is_a('IfcRelContainedInSpatialStructure'):
                        if rel.RelatingStructure and rel.RelatingStructure.is_a('IfcBuildingStorey'):
                            assigned_level = rel.RelatingStructure.Name
                            assignment_method = 'contained_in_spatial'
                            result['diagnostics']['spatial_method_success'] += 1
                            break
            
            # Strategy 2: Property-based level assignment
            if not assigned_level:
                try:
                    psets = ifcopenshell.util.element.get_psets(space)
                    for pset_name, pset_data in psets.items():
                        if any(ps.lower() == pset_name.lower() for ps in level_property_sets):
                            for prop_name, prop_value in pset_data.items():
                                if any(pn.lower() == prop_name.lower() for pn in level_property_names):
                                    assigned_level = str(prop_value)
                                    assignment_method = 'property_based'
                                    result['diagnostics']['property_method_success'] += 1
                                    break
                        if assigned_level:
                            break
                except:
                    pass
            
            # Extract area information
            area = None
            area_method = None
            
            try:
                psets = ifcopenshell.util.element.get_psets(space)
                for pset_name, pset_data in psets.items():
                    if any(aps.lower() == pset_name.lower() for aps in area_property_sets):
                        for prop_name, prop_value in pset_data.items():
                            if any(apn.lower() == prop_name.lower() for apn in area_property_names):
                                try:
                                    area = float(prop_value)
                                    area_method = 'property_based'
                                    result['diagnostics']['area_extraction_success'] += 1
                                    break
                                except (ValueError, TypeError):
                                    continue
                        if area is not None:
                            break
            except:
                pass
            
            # Update space info
            space_info['area'] = area
            space_info['level_assignment_method'] = assignment_method
            space_info['area_extraction_method'] = area_method
            
            # Categorize space
            if assigned_level:
                if assigned_level not in spaces_by_level:
                    spaces_by_level[assigned_level] = []
                spaces_by_level[assigned_level].append(space_info)
            else:
                unassigned_spaces.append(space_info)
        
        # Build result
        result['all_levels_summary'] = {level: len(spaces) for level, spaces in spaces_by_level.items()}
        
        if include_unassigned:
            result['unassigned_spaces'] = unassigned_spaces
        
        # Calculate assignment completeness
        assigned_count = sum(len(spaces) for spaces in spaces_by_level.values())
        if result['total_spaces'] > 0:
            result['assignment_completeness'] = (assigned_count / result['total_spaces']) * 100
        
        # Get target level spaces if specified
        if target_level:
            # Try exact match first
            if target_level in spaces_by_level:
                result['target_level_spaces'] = spaces_by_level[target_level]
            else:
                # Try case-insensitive match
                for level_name, spaces in spaces_by_level.items():
                    if level_name.lower() == target_level.lower():
                        result['target_level_spaces'] = spaces
                        break
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'target_level_spaces': [],
            'all_levels_summary': {},
            'unassigned_spaces': [],
            'assignment_completeness': 0.0,
            'diagnostics': {'error': True},
            'total_spaces': 0
        }