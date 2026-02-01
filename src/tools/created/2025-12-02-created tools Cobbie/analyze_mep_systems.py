import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.system
from typing import List, Dict, Optional, Any, Union

def analyze_mep_systems(
    ifc_file: ifcopenshell.file,
    system_types_filter: Optional[List[str]] = None,
    include_element_details: bool = True,
    group_by_system: bool = True,
    element_types_focus: Optional[List[str]] = None,
    organize_by_category: bool = False,
    include_system_type_grouping: bool = False
) -> Dict[str, Any]:
    """
    Analyzes MEP (Mechanical, Electrical, Plumbing) systems in an IFC model by examining
    distribution systems and their associated physical elements.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        system_types_filter: Optional list of system types to include 
            (e.g., ['AIRCONDITIONING', 'VENTILATION', 'ELECTRICAL'])
        include_element_details: Whether to include detailed element type breakdowns (default True)
        group_by_system: Whether to attempt grouping elements by their associated systems (default True)
        element_types_focus: Optional list of specific element types to focus on
            (e.g., ['IfcFlowSegment', 'IfcPipeSegment', 'IfcDuctSegment', 'IfcCableCarrierSegment'])
        organize_by_category: Whether to automatically organize results by MEP categories (HVAC, Plumbing, Electrical)
        include_system_type_grouping: Whether to group systems by their system_type field
    
    Returns:
        Dict containing:
        - 'systems': List of distribution systems with names, types, and descriptions
        - 'total_elements': Count of all distribution elements
        - 'element_types': Dictionary mapping element types to counts
        - 'elements_by_system': Optional mapping of elements to their systems
        - 'summary_by_category': Elements grouped by MEP category (HVAC, Plumbing, Electrical, etc.)
        - 'focused_elements': Elements matching element_types_focus (if specified)
        - 'systems_by_type': Systems grouped by system_type (if include_system_type_grouping=True)
    
    Example:
        import ifcopenshell
        model = ifcopenshell.open('building.ifc')
        mep_analysis = analyze_mep_systems(model, system_types_filter=['ELECTRICAL', 'HEATING'])
        print(f"Found {mep_analysis['total_elements']} MEP elements")
        
        # Enhanced usage with flow segment focus
        flow_analysis = analyze_mep_systems(
            model, 
            element_types_focus=['IfcFlowSegment', 'IfcPipeSegment', 'IfcDuctSegment'],
            organize_by_category=True,
            include_system_type_grouping=True
        )
    """
    try:
        result = {
            'systems': [],
            'total_elements': 0,
            'element_types': {},
            'elements_by_system': {},
            'summary_by_category': {}
        }
        
        # Get all distribution systems
        distribution_systems = ifc_file.by_type('IfcDistributionSystem')
        
        # Filter systems by type if specified
        for system in distribution_systems:
            system_type = getattr(system, 'PredefinedType', 'NOTDEFINED')
            system_name = system.Name or 'Unnamed'
            system_description = getattr(system, 'LongName', '')
            
            # Apply filter if specified
            if system_types_filter and system_type not in system_types_filter:
                continue
                
            result['systems'].append({
                'name': system_name,
                'type': system_type,
                'description': system_description,
                'ifc_type': system.is_a()
            })
        
        # Get all distribution elements
        distribution_elements = ifc_file.by_type('IfcDistributionElement')
        result['total_elements'] = len(distribution_elements)
        
        # Count elements by type
        element_types = {}
        for element in distribution_elements:
            element_type = element.is_a()
            element_types[element_type] = element_types.get(element_type, 0) + 1
        
        result['element_types'] = element_types
        
        # Add focused elements if specified
        if element_types_focus:
            focused_elements = {}
            focused_total = 0
            for element_type in element_types_focus:
                count = element_types.get(element_type, 0)
                if count > 0:
                    focused_elements[element_type] = count
                    focused_total += count
            result['focused_elements'] = {
                'total_count': focused_total,
                'element_types': focused_elements
            }
        
        # Group elements by system if requested
        if group_by_system:
            system_elements = {}
            for element in distribution_elements:
                try:
                    # Get systems this element belongs to
                    systems = ifcopenshell.util.system.get_element_systems(element)
                    for system in systems:
                        system_name = system.Name or 'Unnamed'
                        if system_name not in system_elements:
                            system_elements[system_name] = []
                        system_elements[system_name].append(element)
                except Exception as e:
                    # Skip elements that can't be processed
                    continue
            
            # Convert to summary format
            for system_name, elements in system_elements.items():
                element_types_in_system = {}
                
                # Apply element_types_focus filter if specified
                elements_to_count = elements
                if element_types_focus:
                    elements_to_count = [elem for elem in elements 
                                       if elem.is_a() in element_types_focus]
                
                for element in elements_to_count:
                    element_type = element.is_a()
                    element_types_in_system[element_type] = element_types_in_system.get(element_type, 0) + 1
                
                if element_types_in_system:  # Only add if there are elements after filtering
                    result['elements_by_system'][system_name] = {
                        'total_elements': len(elements_to_count),
                        'element_types': element_types_in_system
                    }
        
        # Group systems by type if requested
        if include_system_type_grouping:
            systems_by_type = {}
            for system in result['systems']:
                system_type = system['type']
                if system_type not in systems_by_type:
                    systems_by_type[system_type] = []
                systems_by_type[system_type].append({
                    'name': system['name'],
                    'description': system['description'],
                    'ifc_type': system['ifc_type']
                })
            result['systems_by_type'] = systems_by_type
        
        # Create summary by MEP category
        if include_element_details or organize_by_category:
            # Define MEP categories based on element types
            mep_categories = {
                'HVAC': ['IfcAirTerminal', 'IfcDuctSegment', 'IfcDuctFitting', 'IfcDamper', 'IfcFan'],
                'Plumbing': ['IfcPipeSegment', 'IfcPipeFitting', 'IfcSanitaryTerminal', 'IfcValve'],
                'Electrical': ['IfcElectricDistributionBoard', 'IfcLightFixture', 'IfcOutlet', 
                              'IfcCableCarrierSegment', 'IfcCableCarrierFitting', 'IfcProtectiveDevice',
                              'IfcSwitchingDevice'],
                'Heating': ['IfcBoiler', 'IfcSpaceHeater'],
                'Renewable': ['IfcSolarDevice'],
                'Control': ['IfcSensor', 'IfcFlowController'],
                'Equipment': ['IfcUnitaryEquipment']
            }
            
            # Add flow segments to categories if organize_by_category is True
            if organize_by_category:
                mep_categories['HVAC'].extend(['IfcDuctSegment', 'IfcFlowSegment'])
                mep_categories['Plumbing'].extend(['IfcPipeSegment', 'IfcFlowSegment'])
                mep_categories['Electrical'].extend(['IfcCableCarrierSegment'])
            
            for category, element_types_list in mep_categories.items():
                category_count = 0
                category_details = {}
                
                # Apply element_types_focus filter if specified
                types_to_count = element_types_list
                if element_types_focus:
                    types_to_count = [elem_type for elem_type in element_types_list 
                                    if elem_type in element_types_focus]
                
                for element_type in types_to_count:
                    count = element_types.get(element_type, 0)
                    if count > 0:
                        category_count += count
                        category_details[element_type] = count
                
                if category_count > 0:
                    result['summary_by_category'][category] = {
                        'total_elements': category_count,
                        'element_types': category_details
                    }
        
        return result
        
    except Exception as e:
        return {
            'error': f'Failed to analyze MEP systems: {str(e)}',
            'systems': [],
            'total_elements': 0,
            'element_types': {},
            'elements_by_system': {},
            'summary_by_category': {}
        }