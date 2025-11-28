import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def find_fixtures_by_semantic_type(
    ifc_file: ifcopenshell.file,
    fixture_type: str,
    element_types: Optional[List[str]] = None,
    keyword_mapping: Optional[Dict[str, List[str]]] = None,
    validation_fields: Optional[List[str]] = None,
    include_properties: bool = True,
    max_results: int = 100,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Finds building fixtures of a specific semantic type by searching across multiple element types using keyword matching and validation.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        fixture_type: Semantic category of fixtures to find (e.g., 'sanitary', 'lighting', 'hvac')
        element_types: List of IFC element types to search (default: ['IfcFlowTerminal', 'IfcFurnishingElement', 'IfcBuildingElementProxy'])
        keyword_mapping: Dict mapping fixture types to keyword lists (default includes common sanitary, lighting, HVAC keywords in multiple languages)
        validation_fields: List of fields to check for validation (default: ['ObjectType', 'LongName', 'Type'])
        include_properties: Boolean to include element properties in results (default: True)
        max_results: Maximum number of results to return (default: 100)
        case_sensitive: Boolean for case-sensitive matching (default: False)
    
    Returns:
        Dict with:
        - 'fixtures_found': List of fixture dictionaries with details (name, type, properties, validation_score)
        - 'search_summary': Dict with counts by element type and validation statistics
        - 'false_positives_filtered': Count of elements that matched keywords but were filtered out
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = find_fixtures_by_semantic_type(model, 'sanitary')
        >>> print(f"Found {len(result['fixtures_found'])} sanitary fixtures")
    """
    
    # Default parameters
    if element_types is None:
        element_types = ['IfcFlowTerminal', 'IfcFurnishingElement', 'IfcBuildingElementProxy']
    
    if keyword_mapping is None:
        keyword_mapping = {
            'sanitary': ['toilet', 'wc', 'urinal', 'sink', 'washbasin', 'lavatory', 'bidet', 'shower', 'bathtub', 'sanitary', 'bad', 'waschbecken', 'dusche', 'badewanne', 'toilette'],
            'lighting': ['light', 'lamp', 'luminaire', 'fixture', 'leuchte', 'licht', 'beleuchtung'],
            'hvac': ['hvac', 'air', 'conditioning', 'ventilation', 'duct', 'fan', 'klimatechnik', 'lüftung', 'klima']
        }
    
    if validation_fields is None:
        validation_fields = ['ObjectType', 'LongName', 'Type']
    
    # Initialize results
    fixtures_found = []
    search_summary = {
        'elements_searched': {},
        'keyword_matches': 0,
        'validated_matches': 0,
        'false_positives_filtered': 0
    }
    
    # Get keywords for the requested fixture type
    if fixture_type not in keyword_mapping:
        return {
            'fixtures_found': [],
            'search_summary': search_summary,
            'false_positives_filtered': 0
        }
    
    keywords = keyword_mapping[fixture_type]
    if not case_sensitive:
        keywords = [kw.lower() for kw in keywords]
    
    # Search through each element type
    for elem_type in element_types:
        try:
            elements = ifc_file.by_type(elem_type)
            search_summary['elements_searched'][elem_type] = len(elements)
            
            for element in elements:
                if len(fixtures_found) >= max_results:
                    break
                
                # Get basic element attributes
                name = getattr(element, 'Name', '') or ''
                obj_type = getattr(element, 'ObjectType', '') or ''
                long_name = getattr(element, 'LongName', '') or ''
                global_id = getattr(element, 'GlobalId', '') or ''
                
                # Check for keyword matches in basic attributes
                search_text = f"{name} {obj_type} {long_name}"
                if not case_sensitive:
                    search_text = search_text.lower()
                
                keyword_match = any(keyword in search_text for keyword in keywords)
                
                if keyword_match:
                    search_summary['keyword_matches'] += 1
                    
                    # Validate the match through type relationships and properties
                    validation_score = 0
                    validation_details = {}
                    
                    # Check type relationship
                    type_name = ''
                    if hasattr(element, 'IsDefinedBy'):
                        for rel in element.IsDefinedBy:
                            if rel.is_a('IfcRelDefinesByType'):
                                relating_type = rel.RelatingType
                                type_name = getattr(relating_type, 'Name', '') or ''
                                
                                if not case_sensitive:
                                    type_check = type_name.lower()
                                else:
                                    type_check = type_name
                                
                                if any(keyword in type_check for keyword in keywords):
                                    validation_score += 3
                                    validation_details['type_match'] = type_name
                    
                    # Check properties for validation
                    property_matches = 0
                    properties = {}
                    
                    if include_properties:
                        try:
                            psets = ifcopenshell.util.element.get_psets(element)
                            for pset_name, pset_data in psets.items():
                                if isinstance(pset_data, dict):
                                    for prop_name, prop_value in pset_data.items():
                                        if prop_value is not None:
                                            prop_str = str(prop_value)
                                            if not case_sensitive:
                                                prop_check = prop_str.lower()
                                            else:
                                                prop_check = prop_str
                                            
                                            if any(keyword in prop_check for keyword in keywords):
                                                property_matches += 1
                                                validation_details[f'property_{pset_name}_{prop_name}'] = prop_value
                            
                            if include_properties:
                                properties = psets
                                
                        except Exception:
                            pass  # Property access failed, continue without properties
                    
                    validation_score += min(property_matches, 2)  # Cap property contribution
                    
                    # Determine if this is a valid fixture (higher score = more confident)
                    is_valid_fixture = validation_score >= 2
                    
                    if is_valid_fixture:
                        search_summary['validated_matches'] += 1
                        
                        fixture_info = {
                            'GlobalId': global_id,
                            'Name': name,
                            'ObjectType': obj_type,
                            'LongName': long_name,
                            'ElementClass': elem_type,
                            'Type': type_name,
                            'validation_score': validation_score,
                            'validation_details': validation_details
                        }
                        
                        if include_properties and properties:
                            fixture_info['properties'] = properties
                        
                        fixtures_found.append(fixture_info)
                    else:
                        search_summary['false_positives_filtered'] += 1
                        
        except Exception as e:
            # Handle errors for specific element types gracefully
            search_summary['elements_searched'][elem_type] = 0
            continue
    
    return {
        'fixtures_found': fixtures_found,
        'search_summary': search_summary,
        'false_positives_filtered': search_summary['false_positives_filtered']
    }