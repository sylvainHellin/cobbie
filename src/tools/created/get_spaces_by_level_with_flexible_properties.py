import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Tuple


def get_spaces_by_level_with_flexible_properties(
    ifc_file: ifcopenshell.file,
    level_name: str,
    level_property_sets: List[str] = ['Pset_SpaceCommon', 'Abhängigkeiten', 'Pset_SpaceCustom', 'ArchiCADProperties'],
    level_property_names: List[str] = ['Level', 'Storey', 'Ebene', 'StoreyName'],
    area_property_sets: List[str] = ['BaseQuantities', 'Pset_SpaceCommon', 'PSet_Room', 'BIM.fundamentals', 'ArchiCADQuantities'],
    area_property_names: List[str] = ['Area', 'GrossFloorArea', 'NetFloorArea', 'FloorArea', 'Measured Area'],
    name_field: str = 'LongName',
    case_sensitive: bool = False,
    use_spatial_relationships: bool = True,
    spatial_fallback_to_properties: bool = True,
    additional_property_sources: Optional[List[Tuple[str, str]]] = None,
    additional_property_keywords: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Extracts spaces from a specific building level with their areas and additional properties using flexible 
    property set and property name specifications. This function handles the common variation in IFC models 
    where level, area, and other property information may be stored in different property sets and with 
    different property names than standard conventions.
    
    Enhanced with spatial relationship support and additional property extraction capabilities.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_name: Name of the level to filter by (e.g., 'Ground Floor', 'Erdgeschoss')
        level_property_sets: List of property set names to search for level information. 
            Defaults to common IFC property sets for level information.
        level_property_names: List of property names to search for level information.
            Defaults to common property names for level data.
        area_property_sets: List of property set names to search for area information.
            Defaults to common IFC property sets for area data.
        area_property_names: List of property names to search for area information.
            Defaults to common property names for area data.
        name_field: Field to use for space name display (default: 'LongName')
        case_sensitive: Whether level matching should be case sensitive (default: False)
        use_spatial_relationships: Whether to use spatial relationships as primary filtering method (default: True)
        spatial_fallback_to_properties: Whether to fall back to property-based filtering if spatial method fails (default: True)
        additional_property_sources: List of (property_set, property_name) tuples for specific property extraction
        additional_property_keywords: List of keywords for flexible property discovery
    
    Returns:
        List of dictionaries containing space information with names, areas, and additional properties.
        Each dictionary contains:
        - 'name': Space name (from name_field)
        - 'area': Space area (float or None if not found)
        - 'level': Level name (as found in properties or spatial relationships)
        - 'id': Space ID
        - Additional properties as specified by additional_property_sources and additional_property_keywords
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> # Basic usage (backward compatible)
        >>> spaces = get_spaces_by_level_with_flexible_properties(
        ...     model, level_name='Ground Floor'
        ... )
        >>> # Enhanced usage with additional properties
        >>> spaces = get_spaces_by_level_with_flexible_properties(
        ...     model, 
        ...     level_name='Ground Floor',
        ...     additional_property_sources=[('Pset_SpaceCommon', 'Height'), ('ArchiCADProperties', 'Raumhöhe')],
        ...     additional_property_keywords=['height', 'ceiling', 'höhe']
        ... )
    """
    try:
        # Prepare level name for comparison
        if not case_sensitive:
            level_name_lower = level_name.lower()
        
        # Initialize additional property parameters
        if additional_property_sources is None:
            additional_property_sources = []
        if additional_property_keywords is None:
            additional_property_keywords = []
        
        spaces_data = []
        
        # Iterate through all IfcSpace elements
        for space in ifc_file.by_type('IfcSpace'):
            space_info = {
                'id': getattr(space, 'id', None),
                'name': getattr(space, name_field, getattr(space, 'Name', 'Unnamed')),
                'area': None,
                'level': None
            }
            
            found_level = None
            
            # Method 1: Try spatial relationships first (if enabled)
            if use_spatial_relationships:
                try:
                    # Check Decomposes relationships for building storey
                    for rel in space.Decomposes:
                        if hasattr(rel, 'RelatingObject') and rel.RelatingObject.is_a('IfcBuildingStorey'):
                            storey_name = rel.RelatingObject.Name
                            if not case_sensitive:
                                if level_name_lower == storey_name.lower():
                                    found_level = storey_name
                                    break
                            else:
                                if level_name == storey_name:
                                    found_level = storey_name
                                    break
                    
                    # If not found in Decomposes, try get_container as fallback
                    if not found_level:
                        try:
                            container = ifcopenshell.util.element.get_container(space)
                            if container and container.is_a('IfcBuildingStorey'):
                                storey_name = container.Name
                                if not case_sensitive:
                                    if level_name_lower == storey_name.lower():
                                        found_level = storey_name
                                else:
                                    if level_name == storey_name:
                                        found_level = storey_name
                        except Exception:
                            pass
                            
                except Exception:
                    pass
            
            # Method 2: Fall back to property-based filtering (if spatial failed or disabled)
            if not found_level and spatial_fallback_to_properties:
                try:
                    # Get all property sets for the space
                    psets = {}
                    try:
                        psets = ifcopenshell.util.element.get_psets(space)
                    except Exception:
                        # If get_psets fails, try manual extraction
                        if hasattr(space, 'IsDefinedBy'):
                            for rel in space.IsDefinedBy:
                                if hasattr(rel, 'RelatingPropertyDefinition'):
                                    prop_def = rel.RelatingPropertyDefinition
                                    if hasattr(prop_def, 'HasProperties'):
                                        pset_data = {}
                                        for prop in prop_def.HasProperties:
                                            if hasattr(prop, 'NominalValue'):
                                                value = prop.NominalValue
                                                if hasattr(value, 'wrappedValue'):
                                                    pset_data[prop.Name] = value.wrappedValue
                                                else:
                                                    pset_data[prop.Name] = value
                                        psets[prop_def.Name] = pset_data
                    
                    # Search for level information in properties
                    for pset_name in level_property_sets:
                        if pset_name in psets:
                            for prop_name in level_property_names:
                                if prop_name in psets[pset_name]:
                                    level_value = str(psets[pset_name][prop_name])
                                    if not case_sensitive:
                                        if level_name_lower in level_value.lower():
                                            found_level = level_value
                                            break
                                    else:
                                        if level_name in level_value:
                                            found_level = level_value
                                            break
                            if found_level:
                                break
                    
                    # If level not found in specified property sets, try broader search
                    if not found_level:
                        for pset_name, pset_data in psets.items():
                            for prop_name, prop_value in pset_data.items():
                                if any(keyword in prop_name.lower() for keyword in ['level', 'ebene', 'floor', 'geschoss', 'storey']):
                                    level_value = str(prop_value)
                                    if not case_sensitive:
                                        if level_name_lower in level_value.lower():
                                            found_level = level_value
                                            break
                                    else:
                                        if level_name in level_value:
                                            found_level = level_value
                                            break
                            if found_level:
                                break
                                
                except Exception:
                    pass
            
            # If this space is on the target level, extract all property information
            if found_level:
                space_info['level'] = found_level
                
                # Get all property sets for comprehensive property extraction
                psets = {}
                try:
                    psets = ifcopenshell.util.element.get_psets(space)
                except Exception:
                    # Manual extraction
                    if hasattr(space, 'IsDefinedBy'):
                        for rel in space.IsDefinedBy:
                            if hasattr(rel, 'RelatingPropertyDefinition'):
                                prop_def = rel.RelatingPropertyDefinition
                                if hasattr(prop_def, 'HasProperties'):
                                    pset_data = {}
                                    for prop in prop_def.HasProperties:
                                        if hasattr(prop, 'NominalValue'):
                                            value = prop.NominalValue
                                            if hasattr(value, 'wrappedValue'):
                                                pset_data[prop.Name] = value.wrappedValue
                                            else:
                                                pset_data[prop.Name] = value
                                    psets[prop_def.Name] = pset_data
                
                # Extract area information
                found_area = None
                for pset_name in area_property_sets:
                    if pset_name in psets:
                        for prop_name in area_property_names:
                            if prop_name in psets[pset_name]:
                                area_value = psets[pset_name][prop_name]
                                try:
                                    found_area = float(area_value)
                                    break
                                except (ValueError, TypeError):
                                    continue
                        if found_area is not None:
                            break
                
                # If area not found in specified property sets, try broader search
                if found_area is None:
                    for pset_name, pset_data in psets.items():
                        for prop_name, prop_value in pset_data.items():
                            if any(keyword in prop_name.lower() for keyword in ['area', 'fläche', 'surface', 'gross', 'net']):
                                try:
                                    found_area = float(prop_value)
                                    break
                                except (ValueError, TypeError):
                                    continue
                        if found_area is not None:
                            break
                
                space_info['area'] = found_area
                
                # Extract additional properties from specific sources
                for prop_set_name, prop_name in additional_property_sources:
                    if prop_set_name in psets and prop_name in psets[prop_set_name]:
                        # Create a clean property name for the result
                        clean_prop_name = prop_name.replace(' ', '_').replace('.', '_')
                        space_info[clean_prop_name] = psets[prop_set_name][prop_name]
                
                # Extract additional properties using keyword discovery
                if additional_property_keywords:
                    for pset_name, pset_data in psets.items():
                        for prop_name, prop_value in pset_data.items():
                            # Check if any keyword matches the property name
                            if any(keyword.lower() in prop_name.lower() for keyword in additional_property_keywords):
                                # Create a clean property name for the result
                                clean_prop_name = prop_name.replace(' ', '_').replace('.', '_')
                                space_info[clean_prop_name] = prop_value
                
                spaces_data.append(space_info)
        
        return spaces_data
        
    except Exception as e:
        # Return empty list if any error occurs
        return []