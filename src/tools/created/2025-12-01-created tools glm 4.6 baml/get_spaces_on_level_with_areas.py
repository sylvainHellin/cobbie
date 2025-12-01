import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Union, Optional

def get_spaces_on_level_with_areas(
    ifc_file,
    level_name: str,
    area_property_sets: List[str] = ['Qto_SpaceBaseQuantities', 'Dimensions', 'BaseQuantities', 'Pset_SpaceCustom', 'PSet_Room'],
    area_property_names: List[str] = ['GrossFloorArea', 'NetFloorArea', 'Area', 'FloorArea'],
    include_diagnostics: bool = False,
    level_name_mapping: Optional[Dict[str, str]] = None,
    auto_resolve_level_name: bool = False,
    semantic_mapping_rules: Optional[Dict[str, List[str]]] = None
) -> Union[List[Dict], Dict]:
    """
    Extracts spaces from a specific building level with their areas.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_name: Name of the building level to extract spaces from (e.g., 'Ground Floor', 'First Floor', '4')
        area_property_sets: List of property sets to search for area information
        area_property_names: List of property names to search for area data
        include_diagnostics: Boolean to include diagnostic information
        level_name_mapping: Optional dict mapping semantic level identifiers to actual level names
                             (e.g., {'4': 'OG4', 'ground': 'EG', '1': 'OG1'})
        auto_resolve_level_name: Boolean to enable automatic matching of semantic level names to actual model level names
        semantic_mapping_rules: Optional dict providing custom mapping rules for semantic matching
                                (e.g., {'4': ['OG4', 'Level 4', '4th Floor'], 'ground': ['EG', 'Ground Floor', 'Level 0']})
    
    Returns:
        If include_diagnostics=False: List of dicts with space info [{'id': int, 'name': str, 'area': float, 'level_assignment_method': str, 'area_extraction_method': str}, ...]
        If include_diagnostics=True: Dict with 'spaces' list and 'diagnostics' information
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> # Original usage (backward compatible)
        >>> spaces = get_spaces_on_level_with_areas(ifc_file, 'OG4')
        >>> # Usage with mapping
        >>> mapping = {'4': 'OG4', 'ground': 'EG', '1': 'OG1'}
        >>> spaces = get_spaces_on_level_with_areas(ifc_file, '4', level_name_mapping=mapping)
        >>> # Usage with automatic resolution
        >>> semantic_rules = {'4': ['OG4', 'Level 4', '4th Floor'], 'ground': ['EG', 'Ground Floor', 'Level 0']}
        >>> spaces = get_spaces_on_level_with_areas(ifc_file, '4', auto_resolve_level_name=True, semantic_mapping_rules=semantic_rules)
        >>> print(f"Found {len(spaces)} spaces")
    """
    try:
        # Get all storeys first to enable semantic matching
        storeys = ifc_file.by_type('IfcBuildingStorey')
        storey_map = {storey.id(): storey.Name for storey in storeys}
        available_storeys = list(storey_map.values())
        
        # Apply level name resolution logic
        target_level_name = level_name
        resolution_method = None
        
        # Step 1: Apply explicit mapping if provided
        if level_name_mapping and level_name in level_name_mapping:
            target_level_name = level_name_mapping[level_name]
            resolution_method = 'explicit_mapping'
        
        # Step 2: Apply automatic resolution if enabled and no explicit mapping was used
        elif auto_resolve_level_name:
            # First try exact match
            if level_name in available_storeys:
                target_level_name = level_name
                resolution_method = 'exact_match'
            else:
                # Try semantic matching
                semantic_rules = semantic_mapping_rules or {}
                
                # Check if we have rules for this level
                if level_name in semantic_rules:
                    possible_names = semantic_rules[level_name]
                    for possible_name in possible_names:
                        if possible_name in available_storeys:
                            target_level_name = possible_name
                            resolution_method = 'semantic_mapping'
                            break
                
                # If no rules or no match, try fuzzy matching
                if resolution_method is None:
                    # Try case-insensitive matching
                    for storey_name in available_storeys:
                        if storey_name.lower() == level_name.lower():
                            target_level_name = storey_name
                            resolution_method = 'case_insensitive_match'
                            break
                    
                    # Try partial matching (contains)
                    if resolution_method is None:
                        for storey_name in available_storeys:
                            if level_name.lower() in storey_name.lower() or storey_name.lower() in level_name.lower():
                                target_level_name = storey_name
                                resolution_method = 'partial_match'
                                break
        
        # Get all spaces
        spaces = ifc_file.by_type('IfcSpace')
        
        # Initialize results
        target_spaces = []
        all_spaces_processed = []
        unassigned_spaces = []
        
        # Process each space
        for space in spaces:
            space_info = {
                'id': space.id(),
                'name': space.Name or 'Unknown',
                'area': None,
                'level_assignment_method': None,
                'area_extraction_method': None
            }
            
            # Find which storey this space belongs to
            assigned_storey = None
            if space.Decomposes:
                for rel in space.Decomposes:
                    if hasattr(rel, 'RelatingObject') and rel.RelatingObject:
                        storey_id = rel.RelatingObject.id()
                        storey_name = storey_map.get(storey_id, 'Unknown')
                        assigned_storey = storey_name
                        space_info['level_assignment_method'] = 'decomposes'
                        break
            
            # Extract area from property sets
            all_psets = ifcopenshell.util.element.get_psets(space)
            area_found = False
            
            # Search for area in specified property sets and property names
            for pset_name in area_property_sets:
                if pset_name in all_psets:
                    pset_data = all_psets[pset_name]
                    for prop_name in area_property_names:
                        if prop_name in pset_data:
                            prop_value = pset_data[prop_name]
                            if prop_value is not None and isinstance(prop_value, (int, float)):
                                space_info['area'] = float(prop_value)
                                space_info['area_extraction_method'] = f'property_based_{pset_name}_{prop_name}'
                                area_found = True
                                break
                    if area_found:
                        break
            
            # Add to appropriate collection
            all_spaces_processed.append(space_info)
            
            if assigned_storey == target_level_name:
                target_spaces.append(space_info)
            elif assigned_storey is None:
                unassigned_spaces.append(space_info)
        
        # Prepare result
        if include_diagnostics:
            diagnostics = {
                'total_spaces_processed': len(all_spaces_processed),
                'target_level_spaces_found': len(target_spaces),
                'unassigned_spaces': len(unassigned_spaces),
                'available_storeys': available_storeys,
                'target_level': level_name,
                'mapped_target_level': target_level_name if target_level_name != level_name else None,
                'level_mapping_used': level_name_mapping is not None,
                'auto_resolution_used': auto_resolve_level_name,
                'resolution_method': resolution_method
            }
            return {
                'spaces': target_spaces,
                'diagnostics': diagnostics
            }
        else:
            return target_spaces
            
    except Exception as e:
        if include_diagnostics:
            return {
                'spaces': [],
                'diagnostics': {'error': str(e)}
            }
        else:
            return []