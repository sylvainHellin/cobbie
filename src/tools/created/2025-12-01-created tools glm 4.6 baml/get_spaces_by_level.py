import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Tuple

def get_spaces_by_level(
    ifc_file: ifcopenshell.file,
    level_name: str,
    level_property_set: str = 'Abhängigkeiten',
    level_property_name: str = 'Ebene',
    name_property_set: str = 'ID-Daten',
    include_areas: bool = True,
    residential_identification_keywords: Optional[List[str]] = None,
    residential_property_sources: Optional[List[Tuple[str, str]]] = None,
    include_only_residential: bool = False,
    comprehensive_area_extraction: bool = False
) -> List[Dict[str, Any]]:
    """
    Extracts spaces from a specific building level with their room names, numbers, and areas.
    
    This function handles the common pattern of filtering IfcSpace elements by level information
    and extracting their key properties. It uses proper IFC spatial relationships to find spaces
    on specific building storeys. Enhanced with residential unit identification and comprehensive
    area extraction capabilities.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_name: Name of the level to filter by (e.g., '02 tweede verdieping', 'E00_OKRD')
        level_property_set: Property set containing level info (default: 'Abhängigkeiten') - DEPRECATED
        level_property_name: Property name for level (default: 'Ebene') - DEPRECATED
        name_property_set: Property set containing room names (default: 'ID-Daten')
        include_areas: Whether to attempt area extraction (default: True)
        residential_identification_keywords: List of keywords to identify residential units 
            (default: ['kavel', 'unit', 'apartment', 'woning', 'residential'])
        residential_property_sources: List of (property_set, property_name) tuples to check 
            for residential identification (default: [('Pset_SpaceCommon', 'Category')])
        include_only_residential: If True, filter to include only residential units (default: False)
        comprehensive_area_extraction: If True, try multiple area sources (default: False)
    
    Returns:
        List of dictionaries containing space information: 
        [{'number': str, 'name': str, 'area': str, 'id': int, 'is_residential': bool, 'area_source': str}]
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> # Basic usage (backward compatible)
        >>> spaces = get_spaces_by_level(ifc_file, '02 tweede verdieping')
        >>> # Enhanced usage for residential units
        >>> residential_spaces = get_spaces_by_level(
        ...     ifc_file, '02 tweede verdieping', 
        ...     include_only_residential=True,
        ...     comprehensive_area_extraction=True
        ... )
        >>> for space in spaces:
        ...     print(f"{space['number']}: {space['name']} - {space['area']} m²")
    """
    # Set default values for new parameters
    if residential_identification_keywords is None:
        residential_identification_keywords = ['kavel', 'unit', 'apartment', 'woning', 'residential']
    if residential_property_sources is None:
        residential_property_sources = [('Pset_SpaceCommon', 'Category')]
    
    spaces_on_level = []
    
    try:
        # Find the target storey by name (supporting partial matches)
        target_storey = None
        for storey in ifc_file.by_type('IfcBuildingStorey'):
            if level_name.lower() in storey.Name.lower() or storey.Name.lower() in level_name.lower():
                target_storey = storey
                break
        
        if not target_storey:
            # If no exact match found, try to find storeys with similar names
            import re
            level_num = re.findall(r'\d+', level_name)
            for storey in ifc_file.by_type('IfcBuildingStorey'):
                storey_num = re.findall(r'\d+', storey.Name)
                if level_num and storey_num and level_num[0] == storey_num[0]:
                    target_storey = storey
                    break
        
        if not target_storey:
            return []  # No matching storey found
        
        # Get all elements in the target storey using proper spatial relationships
        elements_in_storey = ifcopenshell.util.element.get_decomposition(target_storey)
        
        # Filter for IfcSpace elements
        spaces_in_storey = [elem for elem in elements_in_storey if elem.is_a() == 'IfcSpace']
        
        for space in spaces_in_storey:
            try:
                # Extract basic space information
                space_info = {
                    'id': space.id(),
                    'number': space.Name or '',
                    'name': space.LongName or '',
                    'area': 'N/A',
                    'is_residential': False,
                    'area_source': 'Not found'
                }
                
                # Get property sets for this space
                psets = ifcopenshell.util.element.get_psets(space)
                
                # Try to get room name and number from the specified property set
                if name_property_set in psets:
                    room_name = psets[name_property_set].get('Name')
                    if room_name:
                        space_info['name'] = room_name
                    
                    room_number = psets[name_property_set].get('Nummer')
                    if room_number:
                        space_info['number'] = room_number
                
                # Check for residential unit identification
                is_residential = False
                
                # Check by keywords in name/number
                for keyword in residential_identification_keywords:
                    if (keyword.lower() in space_info['name'].lower() or 
                        keyword.lower() in space_info['number'].lower()):
                        is_residential = True
                        break
                
                # Check by property sources
                if not is_residential:
                    for prop_set_name, prop_name in residential_property_sources:
                        if prop_set_name in psets:
                            prop_value = psets[prop_set_name].get(prop_name, '')
                            if isinstance(prop_value, str):
                                for keyword in residential_identification_keywords:
                                    if keyword.lower() in prop_value.lower():
                                        is_residential = True
                                        break
                        if is_residential:
                            break
                
                space_info['is_residential'] = is_residential
                
                # Also check Pset_SpaceCommon for additional information
                if 'Pset_SpaceCommon' in psets:
                    category = psets['Pset_SpaceCommon'].get('Category')
                    if category:
                        space_info['category'] = category
                
                # Try to extract area information if requested
                if include_areas:
                    area_found = False
                    
                    if comprehensive_area_extraction:
                        # Try multiple area sources in order of preference
                        area_sources = [
                            # Quantity sets (most reliable)
                            lambda: _extract_area_from_quantities(space),
                            # ArchiCAD properties
                            lambda: _extract_area_from_archicad(psets),
                            # Zone stamp properties
                            lambda: _extract_area_from_zone_stamp(psets),
                            # Generic area properties
                            lambda: _extract_area_from_generic(psets)
                        ]
                        
                        for area_extractor in area_sources:
                            try:
                                area_value, source = area_extractor()
                                if area_value is not None and area_value > 0:
                                    space_info['area'] = f"{area_value:.1f}"
                                    space_info['area_source'] = source
                                    area_found = True
                                    break
                            except Exception:
                                continue
                    else:
                        # Original area extraction logic
                        try:
                            quantities = ifcopenshell.util.element.get_psets(space, qtos_only=True)
                            if isinstance(quantities, dict):
                                # Look for area quantities in all quantity sets
                                for qset_name, qset in quantities.items():
                                    if isinstance(qset, dict):
                                        for q_name, q_value in qset.items():
                                            # Check for various area-related quantity names
                                            area_keywords = ['grossfloorarea', 'netfloorarea', 'area', 'floorarea', 'grossarea']
                                            if any(keyword in q_name.lower() for keyword in area_keywords):
                                                try:
                                                    area_value = float(q_value)
                                                    if area_value > 0:  # Only use positive areas
                                                        space_info['area'] = f"{area_value:.1f}"
                                                        space_info['area_source'] = f'QuantitySet.{q_name}'
                                                        area_found = True
                                                        break
                                                except (ValueError, TypeError):
                                                    continue
                                    if area_found:
                                        break
                        except Exception:
                            # If quantity extraction fails, area remains 'N/A'
                            pass
                
                # Apply residential filter if requested
                if not include_only_residential or is_residential:
                    spaces_on_level.append(space_info)
                
            except Exception:
                # Skip problematic spaces and continue with others
                continue
                
    except Exception:
        # If major error occurs, return empty list
        return []
    
    return spaces_on_level


def _extract_area_from_quantities(space) -> Tuple[Optional[float], str]:
    """Extract area from quantity sets."""
    quantities = ifcopenshell.util.element.get_psets(space, qtos_only=True)
    if isinstance(quantities, dict):
        for qset_name, qset in quantities.items():
            if isinstance(qset, dict):
                for q_name, q_value in qset.items():
                    area_keywords = ['grossfloorarea', 'netfloorarea', 'area', 'floorarea', 'grossarea']
                    if any(keyword in q_name.lower() for keyword in area_keywords):
                        try:
                            area_value = float(q_value)
                            if area_value > 0:
                                return area_value, f'QuantitySet.{q_name}'
                        except (ValueError, TypeError):
                            continue
    return None, 'Not found'


def _extract_area_from_archicad(psets: Dict) -> Tuple[Optional[float], str]:
    """Extract area from ArchiCAD properties."""
    if 'ArchiCADProperties' in psets:
        archicad_props = psets['ArchiCADProperties']
        for prop_name, prop_value in archicad_props.items():
            if any(keyword in prop_name.lower() for keyword in ['oppervl', 'area', 'vierkant', 'm2', 'm²']):
                try:
                    area_value = float(prop_value)
                    if area_value > 0:
                        return area_value, f'ArchiCADProperties.{prop_name}'
                except (ValueError, TypeError):
                    continue
    return None, 'Not found'


def _extract_area_from_zone_stamp(psets: Dict) -> Tuple[Optional[float], str]:
    """Extract area from zone stamp properties."""
    zone_stamp_sets = [key for key in psets.keys() if 'Zone' in key and 'Stempel' in key]
    for zone_set_name in zone_stamp_sets:
        zone_props = psets[zone_set_name]
        for prop_name, prop_value in zone_props.items():
            if 'oppervlak' in prop_name.lower() or 'area' in prop_name.lower():
                try:
                    area_value = float(prop_value)
                    if area_value > 0:
                        return area_value, f'{zone_set_name}.{prop_name}'
                except (ValueError, TypeError):
                    continue
    return None, 'Not found'


def _extract_area_from_generic(psets: Dict) -> Tuple[Optional[float], str]:
    """Extract area from generic property sets."""
    for pset_name, pset in psets.items():
        if isinstance(pset, dict):
            for prop_name, prop_value in pset.items():
                if any(keyword in prop_name.lower() for keyword in ['oppervl', 'area', 'vierkant', 'm2', 'm²', 'surface']):
                    try:
                        area_value = float(prop_value)
                        if area_value > 0:
                            return area_value, f'{pset_name}.{prop_name}'
                    except (ValueError, TypeError):
                        continue
    return None, 'Not found'