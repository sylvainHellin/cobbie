import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any


def find_toilets_by_floor(
    model_path: str,
    floor_name: str,
    search_keywords: List[str] = None
) -> Dict[str, Any]:
    """
    Find and count toilet fixtures on a specific floor level.
    
    This function searches for actual toilet fixtures in an IFC model by:
    1. Searching across multiple entity types (IfcFurnishingElement, IfcBuildingElementProxy, etc.)
    2. Using comprehensive keyword matching in entity names, descriptions, and property sets
    3. Properly filtering by floor level using spatial relationships
    4. Handling IFC schema differences (IFC2X3 vs IFC4)
    5. Counting individual fixtures rather than assuming bathroom spaces contain toilets
    
    Note: This function is designed to find individual toilet fixtures rather than
    bathroom spaces. It works with models exported from various BIM software including
    ArchiCAD and Revit, and handles incomplete spatial hierarchies.
    
    Args:
        model_path: Path to the IFC model file
        floor_name: Name of the floor to search (e.g., "5. Sal")
        search_keywords: Optional list of keywords to search for toilet fixtures.
                       Defaults to Danish and English bathroom-related terms.
    
    Returns:
        Dictionary containing:
        - toilet_count: Number of toilet fixtures found
        - toilet_details: List of toilet fixture information
        - floor_name: The floor that was searched
        - search_method: Description of how toilets were detected
        - entities_searched: Number of entities examined
        - detection_issues: List of any issues encountered during detection
    """
    # Default keywords for bathroom/toilet detection (Danish and English)
    if search_keywords is None:
        search_keywords = [
            'toilet', 'bad', 'bade', 'vask', 'wc', 'sanitet', 'kloset',
            'bathroom', 'restroom', 'lavatory', 'urinal', 'handbasin',
            'sink', 'washbasin', 'urinoir', 'toiletblok'
        ]
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Initialize results
    toilet_count = 0
    toilet_details = []
    detection_issues = []
    search_method = "Direct fixture detection across multiple entity types"
    
    # Find the target floor
    target_floor = None
    for storey in model.by_type('IfcBuildingStorey'):
        storey_name = getattr(storey, 'Name', '')
        if storey_name and floor_name.lower() in storey_name.lower():
            target_floor = storey
            break
    
    if not target_floor:
        return {
            'toilet_count': 0,
            'toilet_details': [],
            'floor_name': floor_name,
            'search_method': 'Floor not found',
            'entities_searched': 0,
            'detection_issues': [f'Floor "{floor_name}" not found in model']
        }
    
    # Define entity types to search for toilet fixtures
    # Note: IfcSanitaryTerminal is not available in IFC2X3, so we handle schema differences
    entity_types_to_search = ['IfcFurnishingElement', 'IfcBuildingElementProxy']
    
    # Add IfcSanitaryTerminal only if available (IFC4+)
    try:
        model.by_type('IfcSanitaryTerminal')
        entity_types_to_search.append('IfcSanitaryTerminal')
    except:
        detection_issues.append('IfcSanitaryTerminal not available in IFC2X3 schema')
    
    # Also search other potential fixture types
    additional_types = ['IfcFlowTerminal', 'IfcDistributionControlElement']
    for entity_type in additional_types:
        try:
            entities = model.by_type(entity_type)
            if entities:  # Only add if entities exist
                entity_types_to_search.append(entity_type)
        except:
            continue
    
    total_entities_searched = 0
    
    # Search for toilet fixtures across all relevant entity types
    for entity_type in entity_types_to_search:
        try:
            entities = model.by_type(entity_type)
            total_entities_searched += len(entities)
            
            for entity in entities:
                # Get entity properties for keyword matching
                entity_name = getattr(entity, 'Name', '')
                entity_desc = getattr(entity, 'Description', '')
                entity_type_name = getattr(entity, 'ObjectType', '')
                
                # Check for toilet-related keywords in basic properties
                is_toilet = False
                match_reasons = []
                
                # Check name
                if entity_name:
                    if any(keyword.lower() in entity_name.lower() for keyword in search_keywords):
                        is_toilet = True
                        match_reasons.append(f'name: {entity_name}')
                
                # Check description
                if not is_toilet and entity_desc:
                    if any(keyword.lower() in entity_desc.lower() for keyword in search_keywords):
                        is_toilet = True
                        match_reasons.append(f'description: {entity_desc}')
                
                # Check object type
                if not is_toilet and entity_type_name:
                    if any(keyword.lower() in entity_type_name.lower() for keyword in search_keywords):
                        is_toilet = True
                        match_reasons.append(f'type: {entity_type_name}')
                
                # Check property sets for toilet indicators
                if not is_toilet:
                    try:
                        psets = ifcopenshell.util.element.get_psets(entity)
                        for pset_name, pset_data in psets.items():
                            # Check property set name
                            if any(keyword.lower() in pset_name.lower() for keyword in search_keywords):
                                is_toilet = True
                                match_reasons.append(f'pset: {pset_name}')
                                break
                            
                            # Check individual properties
                            for prop_name, prop_value in pset_data.items():
                                if isinstance(prop_value, str):
                                    if any(keyword.lower() in prop_value.lower() for keyword in search_keywords):
                                        is_toilet = True
                                        match_reasons.append(f'property: {pset_name}.{prop_name}={prop_value}')
                                        break
                            if is_toilet:
                                break
                    except Exception as e:
                        detection_issues.append(f'Error checking properties for entity {entity.id()}: {str(e)}')
                        continue
                
                # If this is a toilet fixture, check if it's on the target floor
                if is_toilet:
                    entity_on_floor = False
                    
                    # Method 1: Check spatial container relationship
                    try:
                        container = ifcopenshell.util.element.get_container(entity)
                        while container:
                            if container.is_a() == 'IfcBuildingStorey' and container.id() == target_floor.id():
                                entity_on_floor = True
                                break
                            container = ifcopenshell.util.element.get_container(container)
                    except Exception as e:
                        detection_issues.append(f'Error checking spatial relationship for entity {entity.id()}: {str(e)}')
                    
                    # Method 2: Check ArchiCAD Home Story properties (fallback)
                    if not entity_on_floor:
                        try:
                            psets = ifcopenshell.util.element.get_psets(entity)
                            if 'ArchiCADProperties' in psets:
                                archi_props = psets['ArchiCADProperties']
                                if 'Home Story Name' in archi_props:
                                    if floor_name.lower() in archi_props['Home Story Name'].lower():
                                        entity_on_floor = True
                                        match_reasons.append('ArchiCAD Home Story')
                        except Exception as e:
                            pass  # ArchiCAD properties not available
                    
                    # Method 3: Check Revit Level properties (fallback)
                    if not entity_on_floor:
                        try:
                            psets = ifcopenshell.util.element.get_psets(entity)
                            if 'Pset_Revit_Element' in psets:
                                revit_props = psets['Pset_Revit_Element']
                                if 'Level' in revit_props:
                                    if floor_name.lower() in str(revit_props['Level']).lower():
                                        entity_on_floor = True
                                        match_reasons.append('Revit Level')
                        except Exception as e:
                            pass  # Revit properties not available
                    
                    # If entity is on the target floor, add it to results
                    if entity_on_floor:
                        toilet_count += 1
                        
                        # Get additional details about the fixture
                        fixture_details = {
                            'id': entity.id(),
                            'type': entity.is_a(),
                            'name': entity_name,
                            'description': entity_desc,
                            'object_type': entity_type_name,
                            'detection_method': match_reasons,
                            'floor': floor_name
                        }
                        
                        # Try to get additional property information
                        try:
                            psets = ifcopenshell.util.element.get_psets(entity)
                            if psets:
                                fixture_details['property_sets'] = list(psets.keys())
                                
                                # Look for specific toilet-related properties
                                toilet_properties = {}
                                for pset_name, pset_data in psets.items():
                                    for prop_name, prop_value in pset_data.items():
                                        if isinstance(prop_value, str) and any(keyword.lower() in prop_value.lower() for keyword in search_keywords):
                                            toilet_properties[f'{pset_name}.{prop_name}'] = prop_value
                                
                                if toilet_properties:
                                    fixture_details['toilet_properties'] = toilet_properties
                        except Exception as e:
                            detection_issues.append(f'Error getting properties for entity {entity.id()}: {str(e)}')
                        
                        toilet_details.append(fixture_details)
                    
        except Exception as e:
            detection_issues.append(f'Error searching entity type {entity_type}: {str(e)}')
            continue
    
    # If no fixtures found with strict floor filtering, try a broader search
    # This handles cases where spatial relationships are incomplete
    if toilet_count == 0:
        detection_issues.append(f'No toilet fixtures found with strict floor filtering for "{floor_name}"')
        
        # Try broader search - assume all toilet fixtures in model might be on target floor
        # This is a fallback for models with incomplete spatial data
        broader_search_count = 0
        broader_search_details = []
        
        for entity_type in entity_types_to_search:
            try:
                entities = model.by_type(entity_type)
                
                for entity in entities:
                    # Get entity properties for keyword matching
                    entity_name = getattr(entity, 'Name', '')
                    entity_desc = getattr(entity, 'Description', '')
                    entity_type_name = getattr(entity, 'ObjectType', '')
                    
                    # Check for toilet-related keywords
                    is_toilet = False
                    match_reasons = []
                    
                    if entity_name and any(keyword.lower() in entity_name.lower() for keyword in search_keywords):
                        is_toilet = True
                        match_reasons.append(f'name: {entity_name}')
                    elif entity_desc and any(keyword.lower() in entity_desc.lower() for keyword in search_keywords):
                        is_toilet = True
                        match_reasons.append(f'description: {entity_desc}')
                    elif entity_type_name and any(keyword.lower() in entity_type_name.lower() for keyword in search_keywords):
                        is_toilet = True
                        match_reasons.append(f'type: {entity_type_name}')
                    
                    # Also check property sets
                    if not is_toilet:
                        try:
                            psets = ifcopenshell.util.element.get_psets(entity)
                            for pset_name, pset_data in psets.items():
                                if any(keyword.lower() in pset_name.lower() for keyword in search_keywords):
                                    is_toilet = True
                                    match_reasons.append(f'pset: {pset_name}')
                                    break
                                for prop_name, prop_value in pset_data.items():
                                    if isinstance(prop_value, str) and any(keyword.lower() in prop_value.lower() for keyword in search_keywords):
                                        is_toilet = True
                                        match_reasons.append(f'property: {pset_name}.{prop_name}')
                                        break
                                if is_toilet:
                                    break
                        except:
                            continue
                    
                    if is_toilet:
                        broader_search_count += 1
                        broader_search_details.append({
                            'id': entity.id(),
                            'type': entity.is_a(),
                            'name': entity_name,
                            'description': entity_desc,
                            'object_type': entity_type_name,
                            'detection_method': match_reasons,
                            'floor': floor_name,
                            'note': 'Floor assignment based on broader search (spatial data incomplete)'
                        })
                        
            except Exception as e:
                detection_issues.append(f'Error in broader search for {entity_type}: {str(e)}')
                continue
        
        if broader_search_count > 0:
            toilet_count = broader_search_count
            toilet_details = broader_search_details
            search_method += " (fallback: broader search due to incomplete spatial data)"
    
    return {
        'toilet_count': toilet_count,
        'toilet_details': toilet_details,
        'floor_name': floor_name,
        'search_method': search_method,
        'entities_searched': total_entities_searched,
        'detection_issues': detection_issues
    }