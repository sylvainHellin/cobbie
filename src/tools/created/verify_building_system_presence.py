import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.system
import ifcopenshell.util.selector
from typing import Dict, List, Optional, Any

def verify_building_system_presence(
    ifc_file,
    system_domain: str,
    domain_keywords: Optional[List[str]] = None,
    include_distribution_check: bool = True,
    include_detailed_results: bool = False
) -> Dict[str, Any]:
    """
    Verifies whether specific building systems (plumbing, electrical, HVAC, etc.) are present in an IFC model
    using a comprehensive multi-strategy approach.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        system_domain: String specifying the system domain to check (e.g., 'plumbing', 'electrical', 'hvac', 'fire')
        domain_keywords: Optional list of keywords for the domain (auto-generated if not provided)
        include_distribution_check: Boolean to check for distribution systems (default: True)
        include_detailed_results: Boolean to include detailed discovery results (default: False)
    
    Returns:
        Dict containing:
        - system_present: Boolean indicating if the system was found
        - confidence_level: String ('high', 'medium', 'low') based on evidence found
        - discovery_summary: Dict with counts from each discovery strategy
        - evidence_found: List of specific elements/systems that confirm presence
        - detailed_results: Optional detailed results from discovery functions
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = verify_building_system_presence(model, 'plumbing')
        >>> print(f"Plumbing present: {result['system_present']}")
    """
    
    try:
        # Auto-generate domain keywords if not provided
        if domain_keywords is None:
            keyword_mapping = {
                'plumbing': ['plumbing', 'sanitary', 'water', 'drain', 'pipe', 'sewer', 'waste', 'vent', 'fixture', 'toilet', 'sink', 'washbasin', 'urinal', 'shower', 'bathtub'],
                'electrical': ['electrical', 'electric', 'power', 'cable', 'wire', 'conduit', 'switch', 'outlet', 'lighting', 'luminaire', 'panel', 'breaker', 'circuit'],
                'hvac': ['hvac', 'heating', 'ventilation', 'air', 'conditioning', 'duct', 'fan', 'coil', 'chiller', 'boiler', 'air', 'handler'],
                'fire': ['fire', 'sprinkler', 'alarm', 'detector', 'extinguisher', 'hose', 'standpipe', 'firestop']
            }
            domain_keywords = keyword_mapping.get(system_domain.lower(), [system_domain])
        
        # Initialize results
        discovery_summary = {
            'mep_elements_found': 0,
            'keyword_matches_found': 0,
            'distribution_systems_found': 0,
            'proxy_elements_found': 0
        }
        evidence_found = []
        detailed_results = {}
        
        # Strategy 1: Check for MEP-related element types
        mep_element_types = [
            'IfcFlowTerminal', 'IfcFlowSegment', 'IfcFlowController', 'IfcFlowMovingDevice',
            'IfcFlowStorageDevice', 'IfcDistributionElement', 'IfcDistributionPort',
            'IfcDistributionCircuit', 'IfcDistributionSystem', 'IfcPipeSegment',
            'IfcPipeFitting', 'IfcSanitaryTerminal', 'IfcBuildingElementProxy'
        ]
        
        mep_elements = []
        for element_type in mep_element_types:
            elements = ifc_file.by_type(element_type)
            if elements:
                mep_elements.extend(elements)
                discovery_summary['mep_elements_found'] += len(elements)
                
                # Check if elements match domain keywords
                for element in elements[:5]:  # Check first 5 to avoid excessive processing
                    name = getattr(element, 'Name', '').lower()
                    object_type = getattr(element, 'ObjectType', '').lower()
                    predefined_type = getattr(element, 'PredefinedType', '').lower()
                    
                    for keyword in domain_keywords:
                        if keyword in name or keyword in object_type or keyword in predefined_type:
                            evidence_found.append({
                                'type': element_type,
                                'name': getattr(element, 'Name', 'N/A'),
                                'object_type': getattr(element, 'ObjectType', 'N/A'),
                                'predefined_type': getattr(element, 'PredefinedType', 'N/A'),
                                'matched_keyword': keyword
                            })
                            discovery_summary['keyword_matches_found'] += 1
                            break
        
        # Strategy 2: Search for domain keywords in all elements
        try:
            # Get common building element types to search through
            search_element_types = [
                'IfcBuildingElement', 'IfcDistributionElement', 'IfcFlowTerminal',
                'IfcFlowSegment', 'IfcFlowController', 'IfcFlowMovingDevice',
                'IfcFlowStorageDevice', 'IfcBuildingElementProxy'
            ]
            
            for element_type in search_element_types:
                elements = ifc_file.by_type(element_type)
                for element in elements:
                    name = getattr(element, 'Name', '').lower()
                    object_type = getattr(element, 'ObjectType', '').lower()
                    
                    for keyword in domain_keywords:
                        if keyword in name or keyword in object_type:
                            # Avoid duplicates
                            if not any(e['name'] == getattr(element, 'Name', 'N/A') and e['type'] == element_type for e in evidence_found):
                                evidence_found.append({
                                    'type': element_type,
                                    'name': getattr(element, 'Name', 'N/A'),
                                    'object_type': getattr(element, 'ObjectType', 'N/A'),
                                    'matched_keyword': keyword
                                })
                                discovery_summary['keyword_matches_found'] += 1
                                break
        except:
            pass
        
        # Strategy 3: Check for distribution systems
        if include_distribution_check:
            distribution_systems = ifc_file.by_type('IfcDistributionSystem')
            if distribution_systems:
                discovery_summary['distribution_systems_found'] = len(distribution_systems)
                for system in distribution_systems:
                    name = getattr(system, 'Name', '').lower()
                    system_type = getattr(system, 'PredefinedType', '').lower()
                    
                    for keyword in domain_keywords:
                        if keyword in name or keyword in system_type:
                            evidence_found.append({
                                'type': 'IfcDistributionSystem',
                                'name': getattr(system, 'Name', 'N/A'),
                                'system_type': getattr(system, 'PredefinedType', 'N/A'),
                                'matched_keyword': keyword
                            })
                            break
            
            # Also check for other distribution-related elements
            distribution_elements = ifc_file.by_type('IfcDistributionElement')
            if distribution_elements:
                discovery_summary['distribution_systems_found'] += len(distribution_elements)
        
        # Strategy 4: Check proxy elements (often used for MEP when standard types aren't available)
        proxy_elements = ifc_file.by_type('IfcBuildingElementProxy')
        if proxy_elements:
            for element in proxy_elements:
                name = getattr(element, 'Name', '').lower()
                object_type = getattr(element, 'ObjectType', '').lower()
                
                for keyword in domain_keywords:
                    if keyword in name or keyword in object_type:
                        # Avoid duplicates
                        if not any(e['name'] == getattr(element, 'Name', 'N/A') and e['type'] == 'IfcBuildingElementProxy' for e in evidence_found):
                            evidence_found.append({
                                'type': 'IfcBuildingElementProxy',
                                'name': getattr(element, 'Name', 'N/A'),
                                'object_type': getattr(element, 'ObjectType', 'N/A'),
                                'matched_keyword': keyword
                            })
                            discovery_summary['proxy_elements_found'] += 1
                            break
        
        # Determine system presence and confidence level
        total_evidence = len(evidence_found)
        system_present = total_evidence > 0
        
        if total_evidence >= 5:
            confidence_level = 'high'
        elif total_evidence >= 2:
            confidence_level = 'medium'
        elif total_evidence >= 1:
            confidence_level = 'low'
        else:
            confidence_level = 'none'
        
        # Prepare detailed results if requested
        if include_detailed_results:
            detailed_results = {
                'mep_elements_by_type': {},
                'all_evidence': evidence_found
            }
            
            for element_type in mep_element_types:
                elements = ifc_file.by_type(element_type)
                if elements:
                    detailed_results['mep_elements_by_type'][element_type] = [
                        {
                            'id': element.id(),
                            'name': getattr(element, 'Name', 'N/A'),
                            'object_type': getattr(element, 'ObjectType', 'N/A')
                        } for element in elements[:10]  # Limit to first 10
                    ]
        
        return {
            'system_present': system_present,
            'confidence_level': confidence_level,
            'discovery_summary': discovery_summary,
            'evidence_found': evidence_found,
            'detailed_results': detailed_results if include_detailed_results else None
        }
        
    except Exception as e:
        return {
            'system_present': False,
            'confidence_level': 'none',
            'discovery_summary': {'error': str(e)},
            'evidence_found': [],
            'detailed_results': None
        }