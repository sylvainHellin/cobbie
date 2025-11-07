import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.selector
from typing import List, Dict, Any, Optional, Union

def discover_building_systems_comprehensive(
    ifc_file: ifcopenshell.file,
    system_keywords: List[str],
    target_element_types: Optional[List[str]] = None,
    include_related_types: bool = True,
    include_systems: bool = True,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Comprehensively discovers and analyzes building systems in an IFC model using a multi-strategy approach.
    This function systematically searches for systems that may be represented as standard element types,
    BuildingElementProxy elements, or through property-based classifications.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        system_keywords: List of keywords related to the target system (e.g., ['heiz', 'heating', 'wärme', 'warm', 'heater', 'boiler', 'radiator'] for heating)
        target_element_types: Optional list of specific IFC element types to search (default: common MEP types)
        include_related_types: Whether to search related element types like BuildingElementProxy (default: True)
        include_systems: Whether to analyze IfcSystem elements (default: True)
        include_details: Whether to include detailed element information (default: True)
    
    Returns:
        Dict containing:
        - system_elements: Dict of found elements by element type and category
        - total_elements: Total number of system-related elements found
        - element_types_present: List of element types that exist in the model
        - systems_found: List of IfcSystem elements related to the target system
        - discovery_summary: Summary of which discovery strategies succeeded
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> heating_keywords = ['heiz', 'heating', 'wärme', 'warm', 'heater', 'boiler', 'radiator']
        >>> result = discover_building_systems_comprehensive(model, heating_keywords)
        >>> print(f"Found {result['total_elements']} heating elements")
    """
    
    # Initialize result structure
    result = {
        'system_elements': {},
        'total_elements': 0,
        'element_types_present': [],
        'systems_found': [],
        'discovery_summary': {
            'standard_types': False,
            'flow_terminals': False,
            'building_element_proxy': False,
            'systems': False,
            'keyword_search': False
        }
    }
    
    # Default target element types for MEP systems
    if target_element_types is None:
        target_element_types = [
            'IfcFlowTerminal',
            'IfcDistributionControlElement', 
            'IfcEnergyConversionDevice',
            'IfcFlowController',
            'IfcFlowMovingDevice',
            'IfcFlowStorageDevice',
            'IfcElectricDistributionPoint',
            'IfcElectricDistributionBoard',
            'IfcProtectiveDevice',
            'IfcSwitchingDevice',
            'IfcController',
            'IfcSensor',
            'IfcActuator'
        ]
    
    # Related types to search if include_related_types is True
    related_types = ['IfcBuildingElementProxy'] if include_related_types else []
    
    # Combine all element types to search
    all_search_types = target_element_types + related_types
    
    # Strategy 1: Search for standard element types
    try:
        for element_type in all_search_types:
            try:
                elements = ifc_file.by_type(element_type)
                if elements:
                    result['element_types_present'].append(element_type)
                    
                    # Filter elements by keywords
                    matching_elements = []
                    for element in elements:
                        element_info = {
                            'id': element.id(),
                            'GlobalId': element.GlobalId if hasattr(element, 'GlobalId') else None,
                            'Name': element.Name if element.Name else 'No Name',
                            'ObjectType': element.ObjectType if hasattr(element, 'ObjectType') and element.ObjectType else 'No ObjectType',
                            'PredefinedType': element.PredefinedType if hasattr(element, 'PredefinedType') and element.PredefinedType else None
                        }
                        
                        # Check keywords in name, object type, and predefined type
                        text_to_search = ' '.join([
                            element_info['Name'].lower(),
                            element_info['ObjectType'].lower(),
                            (element_info['PredefinedType'] or '').lower()
                        ])
                        
                        if any(keyword.lower() in text_to_search for keyword in system_keywords):
                            matching_elements.append(element_info)
                            
                            # Add property details if requested
                            if include_details:
                                try:
                                    psets = ifcopenshell.util.element.get_psets(element)
                                    element_info['property_sets'] = psets
                                except:
                                    element_info['property_sets'] = {}
                    
                    if matching_elements:
                        result['system_elements'][element_type] = matching_elements
                        result['total_elements'] += len(matching_elements)
                        result['discovery_summary']['standard_types'] = True
                        result['discovery_summary']['keyword_search'] = True
                        
                        # Mark specific strategies as successful
                        if element_type == 'IfcFlowTerminal':
                            result['discovery_summary']['flow_terminals'] = True
                        elif element_type == 'IfcBuildingElementProxy':
                            result['discovery_summary']['building_element_proxy'] = True
                            
            except Exception as e:
                # Element type might not exist in schema, continue to next
                continue
                
    except Exception as e:
        pass
    
    # Strategy 2: Search for IfcSystem elements
    if include_systems:
        try:
            systems = ifc_file.by_type('IfcSystem')
            matching_systems = []
            
            for system in systems:
                system_info = {
                    'id': system.id(),
                    'GlobalId': system.GlobalId if hasattr(system, 'GlobalId') else None,
                    'Name': system.Name if system.Name else 'No Name',
                    'ObjectType': system.ObjectType if hasattr(system, 'ObjectType') and system.ObjectType else 'No ObjectType',
                    'Description': system.Description if hasattr(system, 'Description') and system.Description else None
                }
                
                # Check keywords in system name and description
                text_to_search = ' '.join([
                    system_info['Name'].lower(),
                    system_info['ObjectType'].lower(),
                    (system_info['Description'] or '').lower()
                ])
                
                if any(keyword.lower() in text_to_search for keyword in system_keywords):
                    matching_systems.append(system_info)
                    result['discovery_summary']['systems'] = True
            
            result['systems_found'] = matching_systems
            
        except Exception as e:
            pass
    
    # Strategy 3: Advanced keyword search using selector if standard search didn't find much
    if result['total_elements'] == 0 and system_keywords:
        try:
            # Try to find elements using selector syntax with keywords
            for keyword in system_keywords:
                try:
                    # This is a more advanced search that might catch elements missed by standard search
                    query = f"*[{keyword}]"
                    elements = ifcopenshell.util.selector.filter_elements(ifc_file, query)
                    
                    if elements:
                        for element in elements:
                            element_type = element.is_a()
                            if element_type not in result['system_elements']:
                                result['system_elements'][element_type] = []
                            
                            element_info = {
                                'id': element.id(),
                                'GlobalId': element.GlobalId if hasattr(element, 'GlobalId') else None,
                                'Name': element.Name if element.Name else 'No Name',
                                'ObjectType': element.ObjectType if hasattr(element, 'ObjectType') and element.ObjectType else 'No ObjectType'
                            }
                            
                            result['system_elements'][element_type].append(element_info)
                            result['total_elements'] += 1
                            result['discovery_summary']['keyword_search'] = True
                            
                except:
                    continue
                    
        except Exception as e:
            pass
    
    return result