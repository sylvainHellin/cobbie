import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def discover_mep_systems_by_indirect_evidence(
    ifc_file: ifcopenshell.file,
    mep_keywords: Optional[List[str]] = None,
    analyze_quantities: bool = True,
    analyze_properties: bool = True,
    analyze_spaces: bool = True,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Discovers MEP systems in IFC models through indirect evidence like quantities, properties, and semantic keywords.
    
    This function searches for MEP-related indicators across all element types, analyzes quantity elements,
    property values, and synthesizes findings to determine what MEP systems are planned or installed.
    It's particularly useful for models in early design phases where MEP systems are specified through 
    metadata rather than 3D elements.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        mep_keywords: Optional list of MEP-related keywords. If None, uses default keywords in multiple languages
        analyze_quantities: Boolean to analyze quantity elements for MEP indicators (default: True)
        analyze_properties: Boolean to analyze property elements for MEP indicators (default: True)
        analyze_spaces: Boolean to check which spaces have MEP properties (default: True)
        include_details: Boolean to include detailed element information (default: False)
    
    Returns:
        Dict containing:
        - mep_systems_found: List of detected MEP systems with evidence
        - quantity_indicators: Quantity elements suggesting MEP systems
        - property_indicators: Property elements suggesting MEP systems
        - spaces_with_mep: Spaces that have MEP-related properties
        - summary: Overall assessment of MEP systems present
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = discover_mep_systems_by_indirect_evidence(model)
        >>> print(result['summary'])
        >>> for system in result['mep_systems_found']:
        ...     print(f"{system['system_type']}: {system['confidence']} confidence")
    """
    
    # Default MEP keywords in multiple languages
    if mep_keywords is None:
        mep_keywords = [
            'heiz', 'heating', 'wärme', 'warm', 'heater', 'boiler', 'radiator',
            'strom', 'electric', 'power', 'lighting', 'outlet', 'switch', 'kabel',
            'wasser', 'water', 'sanitary', 'pipe', 'drain', 'sewage',
            'lüftung', 'ventilation', 'air', 'duct', 'hvac', 'climate',
            'mep', 'anlage', 'system', 'technik'
        ]
    
    result = {
        'mep_systems_found': [],
        'quantity_indicators': [],
        'property_indicators': [],
        'spaces_with_mep': [],
        'summary': ''
    }
    
    try:
        # Analyze quantity elements
        if analyze_quantities:
            quantity_indicators = []
            for element in ifc_file:
                if element.is_a().startswith('IfcQuantity'):
                    name = getattr(element, 'Name', '')
                    if any(keyword.lower() in name.lower() for keyword in mep_keywords):
                        indicator = {
                            'id': element.id,
                            'type': element.is_a(),
                            'name': name
                        }
                        
                        # Add specific value based on quantity type
                        if hasattr(element, 'AreaValue'):
                            indicator['value'] = getattr(element, 'AreaValue', None)
                            indicator['unit'] = 'm²'
                        elif hasattr(element, 'LengthValue'):
                            indicator['value'] = getattr(element, 'LengthValue', None)
                            indicator['unit'] = 'm'
                        elif hasattr(element, 'VolumeValue'):
                            indicator['value'] = getattr(element, 'VolumeValue', None)
                            indicator['unit'] = 'm³'
                        
                        if include_details:
                            indicator['element_info'] = element.get_info()
                        
                        quantity_indicators.append(indicator)
            
            result['quantity_indicators'] = quantity_indicators
        
        # Analyze property elements
        if analyze_properties:
            property_indicators = []
            for element in ifc_file:
                if element.is_a() == 'IfcPropertySingleValue':
                    name = getattr(element, 'Name', '')
                    if any(keyword.lower() in name.lower() for keyword in mep_keywords):
                        indicator = {
                            'id': element.id,
                            'type': element.is_a(),
                            'name': name,
                            'value': getattr(element, 'NominalValue', None)
                        }
                        
                        if include_details:
                            indicator['element_info'] = element.get_info()
                        
                        property_indicators.append(indicator)
            
            result['property_indicators'] = property_indicators
        
        # Analyze spaces with MEP properties
        if analyze_spaces:
            spaces_with_mep = []
            for space in ifc_file.by_type('IfcSpace'):
                space_info = {
                    'id': space.id,
                    'name': getattr(space, 'Name', ''),
                    'long_name': getattr(space, 'LongName', ''),
                    'mep_properties': []
                }
                
                # Check property sets for this space
                try:
                    psets = ifcopenshell.util.element.get_psets(space)
                    for pset_name, pset_data in psets.items():
                        for prop_name, prop_value in pset_data.items():
                            if any(keyword.lower() in prop_name.lower() for keyword in mep_keywords):
                                space_info['mep_properties'].append({
                                    'pset_name': pset_name,
                                    'property_name': prop_name,
                                    'value': prop_value
                                })
                except Exception:
                    # Fallback to manual property traversal if get_psets fails
                    for rel in space.IsDefinedBy:
                        if hasattr(rel, 'RelatingPropertyDefinition'):
                            prop_def = rel.RelatingPropertyDefinition
                            if hasattr(prop_def, 'HasProperties'):
                                for prop in prop_def.HasProperties:
                                    prop_name = getattr(prop, 'Name', '')
                                    if any(keyword.lower() in prop_name.lower() for keyword in mep_keywords):
                                        space_info['mep_properties'].append({
                                            'pset_name': getattr(prop_def, 'Name', ''),
                                            'property_name': prop_name,
                                            'value': getattr(prop, 'NominalValue', None)
                                        })
                
                if space_info['mep_properties']:
                    if include_details:
                        space_info['space_info'] = space.get_info()
                    spaces_with_mep.append(space_info)
            
            result['spaces_with_mep'] = spaces_with_mep
        
        # Synthesize findings to determine MEP systems
        mep_systems = []
        
        # Check for heating system evidence
        heating_evidence = []
        for qty in result['quantity_indicators']:
            if any(keyword in qty['name'].lower() for keyword in ['heiz', 'heating', 'wärme', 'radiator']):
                heating_evidence.append(f"Quantity: {qty['name']}")
        
        if heating_evidence:
            mep_systems.append({
                'system_type': 'Heating',
                'evidence': heating_evidence,
                'confidence': 'High' if len(heating_evidence) > 5 else 'Medium'
            })
        
        # Check for ventilation system evidence
        ventilation_evidence = []
        for prop in result['property_indicators']:
            if any(keyword in prop['name'].lower() for keyword in ['ventilation', 'lüftung', 'air']):
                ventilation_evidence.append(f"Property: {prop['name']} = {prop['value']}")
        
        for space in result['spaces_with_mep']:
            for prop in space['mep_properties']:
                if any(keyword in prop['property_name'].lower() for keyword in ['ventilation', 'lüftung', 'air']):
                    ventilation_evidence.append(f"Space {space['name']}: {prop['property_name']} = {prop['value']}")
        
        if ventilation_evidence:
            mep_systems.append({
                'system_type': 'Ventilation',
                'evidence': ventilation_evidence,
                'confidence': 'High' if len(ventilation_evidence) > 3 else 'Medium'
            })
        
        # Check for air conditioning evidence
        ac_evidence = []
        for prop in result['property_indicators']:
            if 'airconditioning' in prop['name'].lower() or 'air conditioning' in prop['name'].lower():
                ac_evidence.append(f"Property: {prop['name']} = {prop['value']}")
        
        for space in result['spaces_with_mep']:
            for prop in space['mep_properties']:
                if 'airconditioning' in prop['property_name'].lower() or 'air conditioning' in prop['property_name'].lower():
                    ac_evidence.append(f"Space {space['name']}: {prop['property_name']} = {prop['value']}")
        
        if ac_evidence:
            # Check if AC is present or just considered
            ac_present = any('TRUE' in str(evidence).upper() for evidence in ac_evidence)
            mep_systems.append({
                'system_type': 'Air Conditioning',
                'evidence': ac_evidence,
                'confidence': 'High' if ac_present else 'Low',
                'status': 'Present' if ac_present else 'Considered but not installed'
            })
        
        # Check for electrical system evidence
        electrical_evidence = []
        for qty in result['quantity_indicators']:
            if any(keyword in qty['name'].lower() for keyword in ['strom', 'electric', 'power', 'kabel']):
                electrical_evidence.append(f"Quantity: {qty['name']}")
        
        for prop in result['property_indicators']:
            if any(keyword in prop['name'].lower() for keyword in ['strom', 'electric', 'power', 'lighting']):
                electrical_evidence.append(f"Property: {prop['name']} = {prop['value']}")
        
        if electrical_evidence:
            mep_systems.append({
                'system_type': 'Electrical',
                'evidence': electrical_evidence,
                'confidence': 'Medium'
            })
        
        # Check for plumbing system evidence
        plumbing_evidence = []
        for qty in result['quantity_indicators']:
            if any(keyword in qty['name'].lower() for keyword in ['wasser', 'water', 'sanitary', 'pipe']):
                plumbing_evidence.append(f"Quantity: {qty['name']}")
        
        for prop in result['property_indicators']:
            if any(keyword in prop['name'].lower() for keyword in ['wasser', 'water', 'sanitary', 'pipe']):
                plumbing_evidence.append(f"Property: {prop['name']} = {prop['value']}")
        
        if plumbing_evidence:
            mep_systems.append({
                'system_type': 'Plumbing',
                'evidence': plumbing_evidence,
                'confidence': 'Medium'
            })
        
        result['mep_systems_found'] = mep_systems
        
        # Generate summary
        if mep_systems:
            system_types = [sys['system_type'] for sys in mep_systems]
            result['summary'] = f"Found evidence for {len(mep_systems)} MEP system(s): {', '.join(system_types)}"
        else:
            result['summary'] = "No MEP systems found in this building model."
        
    except Exception as e:
        result['summary'] = f"Error during analysis: {str(e)}"
    
    return result