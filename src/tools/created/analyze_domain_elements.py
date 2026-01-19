import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def analyze_domain_elements(
    model: ifcopenshell.file,
    domains: Union[str, List[str]] = 'all',
    custom_types: Optional[List[str]] = None,
    include_samples: bool = False,
    max_samples: int = 3,
    return_details: bool = True
) -> Dict[str, Any]:
    """
    Analyzes a BIM model to determine which building system domains are represented.

    This function checks for the presence of relevant IFC types in the model to
    identify which domains (MEP, structural, architectural, etc.) are modeled.
    It is useful for determining model completeness and what analyses are possible.

    Args:
        model: The loaded IFC model instance.
        domains: List of domain names to check. Options: 'mep', 'structural', 
                'architectural', 'fire_protection', 'transportation', or 'all'. 
                Defaults to 'all'.
        custom_types: Optional custom list of IFC types to check (overrides domain presets).
        include_samples: If True, includes sample element names for each found type.
        max_samples: Maximum number of samples to return per type. Default is 3.
        return_details: If True, returns detailed breakdown by IFC type; 
                        if False, returns summary by domain. Default is True.

    Returns:
        Dict[str, Any]: A dictionary containing analysis results with the structure:
        {
            'domains': {
                'domain_name': {
                    'present': bool,
                    'type_count': int,
                    'element_count': int,
                    'types_found': Dict[str, int],  // IFC type -> count
                    'samples': Optional[Dict[str, List[str]]] // If include_samples=True
                }
            },
            'summary': {
                'total_types_checked': int,
                'domains_present': List[str],
                'domains_absent': List[str]
            }
        }

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> analysis = analyze_domain_elements(model, domains=['mep', 'structural'])
        >>> print(analysis['summary']['domains_present'])
        ['structural']
    """
    # Predefined domain type mappings
    domain_mappings = {
        'mep': [
            'IfcDistributionSystem', 'IfcFlowTerminal', 'IfcFlowController', 
            'IfcFlowMovingDevice', 'IfcFlowStorageDevice', 'IfcFlowFitting', 
            'IfcFlowSegment', 'IfcDistributionPort', 'IfcDistributionElement', 
            'IfcEnergyConversionDevice', 'IfcElectricElement', 
            'IfcElectricDistributionBoard', 'IfcLamp', 'IfcLightFixture', 
            'IfcActuator', 'IfcSensor', 'IfcController'
        ],
        'structural': [
            'IfcColumn', 'IfcBeam', 'IfcSlab', 'IfcFooting', 
            'IfcPile', 'IfcMember', 'IfcPlate', 'IfcReinforcingBar', 
            'IfcTendon', 'IfcTendonAnchor'
        ],
        'fire_protection': [
            'IfcFireSuppressionTerminal', 'IfcProtectiveDevice', 
            'IfcAlarm', 'IfcFireBlocking', 'IfcFireBreak'
        ],
        'transportation': [
            'IfcStair', 'IfcRamp', 'IfcRampFlight', 'IfcLift', 
            'IfcElevator', 'IfcEscalator'
        ],
        'architectural': [
            'IfcDoor', 'IfcWindow', 'IfcCovering', 'IfcFurnishingElement', 
            'IfcBuildingElementProxy', 'IfcSpace', 'IfcRailing'
        ]
    }

    results: Dict[str, Any] = {
        'domains': {},
        'summary': {
            'total_types_checked': 0,
            'domains_present': [],
            'domains_absent': []
        }
    }

    # Determine which domains to process
    domains_to_check: List[str] = []
    if custom_types:
        # If custom types are provided, create a special 'custom' domain
        domains_to_check = ['custom']
        domain_mappings['custom'] = custom_types
    elif domains == 'all':
        domains_to_check = list(domain_mappings.keys())
    elif isinstance(domains, str) and domains in domain_mappings:
        domains_to_check = [domains]
    elif isinstance(domains, list):
        # Filter valid domain names
        domains_to_check = [d for d in domains if d in domain_mappings]
    
    # Analyze each domain
    for domain_name in domains_to_check:
        types_in_domain = domain_mappings.get(domain_name, [])
        if not types_in_domain:
            continue

        domain_result: Dict[str, Any] = {
            'present': False,
            'type_count': 0,
            'element_count': 0,
            'types_found': {}
        }

        if include_samples:
            domain_result['samples'] = {}

        for ifc_type in types_in_domain:
            results['summary']['total_types_checked'] += 1
            
            try:
                # Attempt to get elements of this type
                elements = model.by_type(ifc_type)
                count = len(elements)
                
                if count > 0:
                    domain_result['present'] = True
                    domain_result['type_count'] += 1
                    domain_result['element_count'] += count
                    
                    if return_details:
                        domain_result['types_found'][ifc_type] = count
                    
                    if include_samples:
                        sample_names = []
                        # Defensive iteration in case an element is malformed
                        for elem in elements[:max_samples]:
                            try:
                                name = getattr(elem, 'Name', 'Unnamed')
                                # Ensure name is a string
                                if not isinstance(name, str):
                                    name = str(name)
                                sample_names.append(name)
                            except (AttributeError, RuntimeError):
                                sample_names.append('Error reading name')
                        domain_result['samples'][ifc_type] = sample_names
            
            except RuntimeError:
                # This occurs if the type does not exist in the model's IFC schema version
                # (e.g., querying Ifc4 types in an IFC2x3 file). 
                # We simply skip these types as they are not applicable to the schema.
                pass
            except AttributeError:
                # Unexpected attribute error during type query, skip type
                pass

        results['domains'][domain_name] = domain_result
        
        if domain_result['present']:
            results['summary']['domains_present'].append(domain_name)
        else:
            results['summary']['domains_absent'].append(domain_name)

    return results