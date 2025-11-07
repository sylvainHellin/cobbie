import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def get_spaces_by_level(
    ifc_file: ifcopenshell.file,
    level_name: str,
    level_property_set: str = 'Abhängigkeiten',
    level_property_name: str = 'Ebene',
    name_property_set: str = 'ID-Daten',
    include_areas: bool = True
) -> List[Dict[str, Any]]:
    """
    Extracts spaces from a specific building level with their room names, numbers, and areas.
    
    This function handles the common pattern of filtering IfcSpace elements by level information
    and extracting their key properties. It uses proper IFC spatial relationships to find spaces
    on specific building storeys.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        level_name: Name of the level to filter by (e.g., '02 tweede verdieping', 'E00_OKRD')
        level_property_set: Property set containing level info (default: 'Abhängigkeiten') - DEPRECATED
        level_property_name: Property name for level (default: 'Ebene') - DEPRECATED
        name_property_set: Property set containing room names (default: 'ID-Daten')
        include_areas: Whether to attempt area extraction (default: True)
    
    Returns:
        List of dictionaries containing space information: 
        [{'number': str, 'name': str, 'area': str, 'id': int}]
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> spaces = get_spaces_by_level(ifc_file, '02 tweede verdieping')
        >>> for space in spaces:
        ...     print(f"{space['number']}: {space['name']} - {space['area']} m²")
    """
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
                    'area': 'N/A'
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
                
                # Also check Pset_SpaceCommon for additional information
                if 'Pset_SpaceCommon' in psets:
                    category = psets['Pset_SpaceCommon'].get('Category')
                    if category:
                        space_info['category'] = category
                
                # Try to extract area information if requested
                if include_areas:
                    try:
                        quantities = ifcopenshell.util.element.get_psets(space, qtos_only=True)
                        if isinstance(quantities, dict):
                            # Look for area quantities in all quantity sets
                            area_found = False
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
                                                    area_found = True
                                                    break
                                            except (ValueError, TypeError):
                                                continue
                                if area_found:
                                    break
                    except Exception:
                        # If quantity extraction fails, area remains 'N/A'
                        pass
                
                spaces_on_level.append(space_info)
                
            except Exception:
                # Skip problematic spaces and continue with others
                continue
                
    except Exception:
        # If major error occurs, return empty list
        return []
    
    return spaces_on_level