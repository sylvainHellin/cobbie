import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.system
from typing import Dict, List, Any, Optional

def analyze_mep_systems_presence(
    ifc_file: ifcopenshell.file,
    system_categories: Optional[Dict[str, List[str]]] = None,
    include_system_elements: bool = True,
    include_element_details: bool = False,
    max_examples_per_type: int = 3,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes the presence and inventory of MEP (Mechanical, Electrical, Plumbing) systems in an IFC model.
    
    This function provides comprehensive system discovery by checking for standard MEP IFC types
    across multiple system categories and returns diagnostic information about what systems are installed.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        system_categories: Dict mapping system names to their IFC types. If None, uses default categories:
            - plumbing: pipes, fittings, sanitary terminals, flow elements
            - electrical: cables, conduits, fixtures, distribution elements
            - hvac: ducts, air terminals, fans, coils
            - fire_protection: sprinklers, fire pumps, alarm systems
        include_system_elements: Boolean to include IfcSystem/IfcDistributionSystem analysis
        include_element_details: Boolean to include detailed element information
        max_examples_per_type: Maximum examples to show per element type
        case_sensitive: Boolean for string matching in element names and types
    
    Returns:
        Dict containing:
        - 'systems_present': List of system categories that have elements
        - 'systems_absent': List of system categories with no elements
        - 'element_counts': Dict mapping system names to element counts by type
        - 'total_elements': Total number of MEP elements found
        - 'system_elements': Information about IfcSystem/IfcDistributionSystem elements
        - 'diagnostic_summary': Summary of model's MEP content
        - 'element_details': Detailed information about elements (if requested)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_mep_systems_presence(model)
        >>> print(result['systems_present'])
        ['plumbing', 'electrical']
    """
    
    try:
        # Default system categories if not provided
        if system_categories is None:
            system_categories = {
                'plumbing': [
                    'IfcPipeSegment', 'IfcPipeFitting', 'IfcSanitaryTerminal',
                    'IfcFlowTerminal', 'IfcFlowController', 'IfcFlowMovingDevice',
                    'IfcFlowStorageDevice', 'IfcFlowSegment'
                ],
                'electrical': [
                    'IfcCableSegment', 'IfcCableFitting', 'IfcCableCarrierSegment',
                    'IfcCableCarrierFitting', 'IfcElectricDistributionPoint',
                    'IfcElectricFlowStorageDevice', 'IfcElectricTimeControl',
                    'IfcLamp', 'IfcLightFixture', 'IfcSwitchingDevice'
                ],
                'hvac': [
                    'IfcDuctSegment', 'IfcDuctFitting', 'IfcAirTerminal',
                    'IfcAirTerminalBox', 'IfcFlowMovingDevice', 'IfcCoil',
                    'IfcUnitaryEquipment', 'IfcSpaceHeater', 'IfcSpaceCooler'
                ],
                'fire_protection': [
                    'IfcFireSuppressionTerminal', 'IfcProtectiveDevice',
                    'IfcProtectiveDeviceTrippingUnit', 'IfcAlarm',
                    'IfcFireSensor', 'IfcFireGenerator'
                ]
            }
        
        # Initialize result structure
        result = {
            'systems_present': [],
            'systems_absent': [],
            'element_counts': {},
            'total_elements': 0,
            'system_elements': {},
            'diagnostic_summary': '',
            'element_details': {}
        }
        
        # Analyze each system category
        for system_name, ifc_types in system_categories.items():
            system_element_count = 0
            type_counts = {}
            element_details = []
            
            for ifc_type in ifc_types:
                try:
                    elements = ifc_file.by_type(ifc_type)
                    element_count = len(elements)
                    
                    if element_count > 0:
                        type_counts[ifc_type] = element_count
                        system_element_count += element_count
                        
                        # Collect element details if requested
                        if include_element_details:
                            type_details = []
                            for i, elem in enumerate(elements[:max_examples_per_type]):
                                name = getattr(elem, 'Name', 'No Name')
                                obj_type = getattr(elem, 'ObjectType', 'No ObjectType')
                                global_id = getattr(elem, 'GlobalId', 'No ID')
                                
                                type_details.append({
                                    'name': name,
                                    'object_type': obj_type,
                                    'global_id': global_id
                                })
                            
                            element_details.append({
                                'ifc_type': ifc_type,
                                'total_count': element_count,
                                'examples': type_details
                            })
                except Exception:
                    # Skip invalid IFC types
                    continue
            
            # Store results for this system
            if system_element_count > 0:
                result['systems_present'].append(system_name)
                result['element_counts'][system_name] = type_counts
                if include_element_details:
                    result['element_details'][system_name] = element_details
                result['total_elements'] += system_element_count
            else:
                result['systems_absent'].append(system_name)
        
        # Analyze system elements (IfcSystem, IfcDistributionSystem)
        if include_system_elements:
            try:
                # Check for IfcSystem elements
                ifc_systems = ifc_file.by_type('IfcSystem')
                result['system_elements']['IfcSystem'] = []
                
                for system in ifc_systems[:max_examples_per_type]:
                    name = getattr(system, 'Name', 'No Name')
                    obj_type = getattr(system, 'ObjectType', 'No ObjectType')
                    description = getattr(system, 'Description', 'No Description')
                    
                    result['system_elements']['IfcSystem'].append({
                        'name': name,
                        'object_type': obj_type,
                        'description': description
                    })
                
                # Check for IfcDistributionSystem elements
                dist_systems = ifc_file.by_type('IfcDistributionSystem')
                result['system_elements']['IfcDistributionSystem'] = []
                
                for system in dist_systems[:max_examples_per_type]:
                    name = getattr(system, 'Name', 'No Name')
                    obj_type = getattr(system, 'ObjectType', 'No ObjectType')
                    
                    # Try to get system type (if available)
                    system_type = 'Unknown'
                    try:
                        if hasattr(system, 'LongName') and system.LongName:
                            system_type = system.LongName
                    except:
                        pass
                    
                    result['system_elements']['IfcDistributionSystem'].append({
                        'name': name,
                        'object_type': obj_type,
                        'system_type': system_type
                    })
                    
            except Exception as e:
                result['system_elements']['error'] = str(e)
        
        # Generate diagnostic summary
        if result['total_elements'] == 0:
            result['diagnostic_summary'] = 'No MEP systems detected in the model. The model appears to contain only architectural and structural elements.'
        elif len(result['systems_present']) == 1:
            result['diagnostic_summary'] = f'Model contains {result["systems_present"][0]} systems with {result["total_elements"]} total elements.'
        else:
            systems_str = ', '.join(result['systems_present'])
            result['diagnostic_summary'] = f'Model contains multiple MEP systems ({systems_str}) with {result["total_elements"]} total elements.'
        
        return result
        
    except Exception as e:
        return {
            'error': f'Error analyzing MEP systems: {str(e)}',
            'systems_present': [],
            'systems_absent': [],
            'element_counts': {},
            'total_elements': 0,
            'system_elements': {},
            'diagnostic_summary': 'Analysis failed due to error',
            'element_details': {}
        }