import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional

def discover_and_categorize_mep_components(
    ifc_file,
    mep_element_types: Optional[List[str]] = None,
    categorization_keywords: Optional[List[str]] = None,
    include_details: bool = False,
    fallback_to_proxy: bool = True
) -> Dict[str, Any]:
    """
    Discovers and categorizes MEP components in an IFC model using a multi-strategy approach.
    
    This function implements a comprehensive workflow needed to find MEP components that may be
    represented as standard MEP element types, BuildingElementProxy elements, or other non-standard
    representations. It tries multiple discovery strategies in sequence and provides categorized
    results with counts.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        mep_element_types: Optional list of MEP element types to search (default: standard MEP types)
        categorization_keywords: Optional list of keywords for categorizing BuildingElementProxy elements
            (default: includes comprehensive MEP, parking, and infrastructure terms)
        include_details: Whether to include detailed element information (default: False)
        fallback_to_proxy: Whether to analyze BuildingElementProxy elements when standard types aren't found (default: True)
    
    Returns:
        Dict[str, Any] containing:
            - 'standard_mep_components': Dict of standard MEP element types and their counts
            - 'proxy_components': Dict of categorized BuildingElementProxy components and their counts
            - 'total_count': Total number of MEP components found
            - 'discovery_strategy': Which strategy was successful
            - 'details': Optional detailed element information if include_details=True
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = discover_and_categorize_mep_components(model)
        >>> print(f"Found {result['total_count']} MEP components")
    """
    
    # Default MEP element types if not provided (excluding IfcBuildingElementProxy)
    if mep_element_types is None:
        mep_element_types = [
            'IfcFlowTerminal', 'IfcFlowSegment', 'IfcFlowController', 'IfcFlowMovingDevice',
            'IfcFlowStorageDevice', 'IfcDistributionElement', 'IfcDistributionFlowElement',
            'IfcDistributionControlElement', 'IfcElectricElement', 'IfcElectricDistributionPoint',
            'IfcElectricFlowStorageDevice', 'IfcElectricMotor', 'IfcElectricTimeControl',
            'IfcElectricTransformer', 'IfcElectricGenerator', 'IfcElectricAppliance',
            'IfcLightFixture', 'IfcSpaceHeater', 'IfcAirTerminal', 'IfcAirTerminalBox',
            'IfcDuctSegment', 'IfcDuctFitting', 'IfcDuctSilencer', 'IfcPipeSegment',
            'IfcPipeFitting', 'IfcPump', 'IfcValve', 'IfcFilter', 'IfcCoolingTower',
            'IfcChiller', 'IfcBoiler', 'IfcHeatExchanger', 'IfcFan', 'IfcCoil',
            'IfcUnitaryEquipment'
        ]
    
    # Expanded default categorization keywords including parking and infrastructure terms
    if categorization_keywords is None:
        categorization_keywords = [
            # Traditional MEP terms (English)
            'ventil', 'hvac', 'heat', 'cool', 'pump', 'fan', 'valve', 'duct',
            'pipe', 'electric', 'light', 'mechanical', 'water', 'drain', 'outlet', 
            'supply', 'return', 'flow', 'segment', 'fitting', 'terminal', 'controller', 
            'storage', 'moving', 'distribution', 'chiller', 'boiler', 'coil', 'filter',
            
            # Traditional MEP terms (Dutch/German)
            'installatie', 'techniek', 'afvoer', 'hwa', 'koud', 'warm', 'riool', 
            'leiding', 'pomp', 'ventilatie', 'verwarming', 'koeling',
            
            # Parking and infrastructure terms (English)
            'parking', 'garage', 'park', 'charging', 'station', 'charge', 'ev', 
            'electric vehicle', 'car', 'vehicle', 'protection', 'barrier', 'guard',
            'bollard', 'post', 'safety', 'traffic', 'road', 'drive', 'access',
            
            # Parking and infrastructure terms (German)
            'parkplatz', 'garage', 'ladestation', 'lade', 'e-ladestation', 'anfahrschutz',
            'schutz', 'rohr', 'fahrzeug', 'auto', 'kfz', 'stellplatz', 'parkhaus',
            
            # General equipment terms
            'equipment', 'device', 'fixture', 'appliance', 'unit', 'system', 'installation'
        ]
    
    result = {
        'standard_mep_components': {},
        'proxy_components': {},
        'total_count': 0,
        'discovery_strategy': 'none',
        'details': {}
    }
    
    try:
        # Strategy 1: Search for standard MEP element types (excluding BuildingElementProxy)
        standard_mep_found = False
        for element_type in mep_element_types:
            try:
                elements = ifc_file.by_type(element_type)
                if elements:
                    result['standard_mep_components'][element_type] = len(elements)
                    standard_mep_found = True
                    
                    if include_details:
                        result['details'][element_type] = []
                        for elem in elements:
                            elem_info = {
                                'id': elem.id(),
                                'Name': getattr(elem, 'Name', None),
                                'ObjectType': getattr(elem, 'ObjectType', None),
                                'GlobalId': getattr(elem, 'GlobalId', None)
                            }
                            result['details'][element_type].append(elem_info)
            except Exception:
                continue
        
        # Strategy 2: Always analyze BuildingElementProxy elements if fallback is enabled
        proxy_mep_found = False
        if fallback_to_proxy:
            try:
                proxy_elements = ifc_file.by_type('IfcBuildingElementProxy')
                if proxy_elements:
                    # Categorize proxy elements by ObjectType and Name using keywords
                    categorized_proxies = {}
                    uncategorized_proxies = []
                    
                    for proxy in proxy_elements:
                        obj_type = getattr(proxy, 'ObjectType', None)
                        name = getattr(proxy, 'Name', None)
                        
                        # Check if this proxy element is MEP-related
                        is_mep = False
                        category = 'Uncategorized'
                        
                        # Combine ObjectType and Name for analysis
                        combined_text = ''
                        if obj_type:
                            combined_text += obj_type.lower()
                        if name:
                            combined_text += ' ' + name.lower()
                        
                        # Check for MEP/Infrastructure keywords
                        for keyword in categorization_keywords:
                            if keyword in combined_text:
                                is_mep = True
                                
                                # Enhanced categorization logic
                                combined_lower = combined_text.lower()
                                
                                # Parking and charging equipment
                                if any(kw in combined_lower for kw in ['ladestation', 'charging', 'e-ladestation']):
                                    category = 'Charging Station'
                                elif any(kw in combined_lower for kw in ['parkplatz', 'parking', 'park']):
                                    category = 'Parking Space'
                                elif any(kw in combined_lower for kw in ['anfahrschutz', 'schutz', 'protection', 'barrier']):
                                    category = 'Protection Barrier'
                                
                                # Traditional MEP categories
                                elif any(kw in combined_lower for kw in ['pipe', 'leitung', 'rohr']):
                                    category = 'Pipe Segment'
                                elif any(kw in combined_lower for kw in ['duct']):
                                    category = 'Duct Segment'
                                elif any(kw in combined_lower for kw in ['valve']):
                                    category = 'Valve'
                                elif any(kw in combined_lower for kw in ['pump', 'pomp']):
                                    category = 'Pump'
                                elif any(kw in combined_lower for kw in ['fan']):
                                    category = 'Fan'
                                elif any(kw in combined_lower for kw in ['ventil', 'ventilatie']):
                                    category = 'Ventilation Component'
                                elif any(kw in combined_lower for kw in ['light', 'licht', 'leuchte']):
                                    category = 'Lighting Equipment'
                                elif any(kw in combined_lower for kw in ['electric', 'elektrisch', 'strom']):
                                    category = 'Electrical Equipment'
                                elif any(kw in combined_lower for kw in ['afvoer', 'water', 'drain']):
                                    category = 'Plumbing Component'
                                elif any(kw in combined_lower for kw in ['hwa', 'warm', 'heat']):
                                    category = 'Heating Component'
                                elif any(kw in combined_lower for kw in ['koud', 'cool']):
                                    category = 'Cooling Component'
                                else:
                                    # Use ObjectType or Name as category if available
                                    category = obj_type if obj_type else (name if name else 'Infrastructure Component')
                                break
                        
                        if is_mep:
                            if category not in categorized_proxies:
                                categorized_proxies[category] = []
                            
                            if include_details:
                                elem_info = {
                                    'id': proxy.id(),
                                    'Name': name,
                                    'ObjectType': obj_type,
                                    'GlobalId': getattr(proxy, 'GlobalId', None)
                                }
                                categorized_proxies[category].append(elem_info)
                            else:
                                categorized_proxies[category].append(proxy)
                        else:
                            uncategorized_proxies.append(proxy)
                    
                    # Convert to counts
                    for category, elements in categorized_proxies.items():
                        result['proxy_components'][category] = len(elements)
                    
                    if uncategorized_proxies:
                        result['proxy_components']['Uncategorized'] = len(uncategorized_proxies)
                    
                    if result['proxy_components']:
                        proxy_mep_found = True
                        
                        if include_details:
                            result['details']['proxy_components'] = categorized_proxies
                            if uncategorized_proxies:
                                result['details']['uncategorized'] = [
                                    {
                                        'id': proxy.id(),
                                        'Name': getattr(proxy, 'Name', None),
                                        'ObjectType': getattr(proxy, 'ObjectType', None),
                                        'GlobalId': getattr(proxy, 'GlobalId', None)
                                    }
                                    for proxy in uncategorized_proxies
                                ]
            
            except Exception as e:
                # Log error but continue
                pass
        
        # Determine discovery strategy and calculate total
        if standard_mep_found and proxy_mep_found:
            result['discovery_strategy'] = 'combined'
            result['total_count'] = sum(result['standard_mep_components'].values()) + sum(result['proxy_components'].values())
        elif standard_mep_found:
            result['discovery_strategy'] = 'standard_mep_types'
            result['total_count'] = sum(result['standard_mep_components'].values())
        elif proxy_mep_found:
            result['discovery_strategy'] = 'building_element_proxy'
            result['total_count'] = sum(result['proxy_components'].values())
        else:
            result['discovery_strategy'] = 'none_found'
        
        return result
        
    except Exception as e:
        # Handle unexpected errors
        result['discovery_strategy'] = 'error'
        result['error'] = str(e)
        return result