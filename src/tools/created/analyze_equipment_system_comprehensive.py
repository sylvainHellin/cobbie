import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.system
from typing import List, Dict, Any, Optional, Union

def analyze_equipment_system_comprehensive(
    ifc_file: ifcopenshell.file,
    primary_equipment_type: str,
    related_equipment_types: Optional[List[str]] = None,
    include_systems: bool = True,
    include_connections: bool = True
) -> Dict[str, Any]:
    """
    Provides comprehensive analysis of equipment systems in a BIM model.
    
    This function performs a multi-level investigation:
    1) Finds and categorizes the primary equipment type
    2) Explores related equipment types that might be part of the same system
    3) Analyzes system connections and relationships
    4) Extracts detailed property sets and manufacturer information
    5) Identifies connected elements and system context
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file object)
        primary_equipment_type: Main IFC type to analyze (e.g., 'IfcUnitaryEquipment')
        related_equipment_types: Optional list of related IFC types to explore
        include_systems: Whether to include system analysis
        include_connections: Whether to include connection analysis
    
    Returns:
        Dict containing:
        - 'primary_equipment': Analysis of primary equipment type
        - 'related_equipment': Analysis of related equipment types
        - 'systems': System information (if include_systems=True)
        - 'connections': Connection information (if include_connections=True)
        - 'summary': Summary statistics
    
    Example:
        model = ifcopenshell.open('model.ifc')
        result = analyze_equipment_system_comprehensive(
            model,
            'IfcUnitaryEquipment',
            ['IfcAirTerminal', 'IfcFan'],
            include_systems=True,
            include_connections=True
        )
    """
    result = {
        'primary_equipment': {},
        'related_equipment': {},
        'systems': {},
        'connections': {},
        'summary': {}
    }
    
    primary_elements = []
    
    try:
        # 1. Analyze primary equipment type
        primary_elements = ifc_file.by_type(primary_equipment_type)
        result['primary_equipment'] = {
            'type': primary_equipment_type,
            'count': len(primary_elements),
            'elements': []
        }
        
        for element in primary_elements:
            element_data = {
                'global_id': element.GlobalId,
                'name': element.Name,
                'object_type': getattr(element, 'ObjectType', None),
                'predefined_type': getattr(element, 'PredefinedType', None),
                'properties': {},
                'systems': [],
                'connections': {'to': [], 'from': []}
            }
            
            # Get properties
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                element_data['properties'] = psets
            except Exception as e:
                element_data['properties'] = {'error': str(e)}
            
            # Get systems
            if include_systems:
                try:
                    systems = ifcopenshell.util.system.get_element_systems(element)
                    element_data['systems'] = [{
                        'name': sys.Name,
                        'type': sys.is_a(),
                        'object_type': getattr(sys, 'ObjectType', None),
                        'predefined_type': getattr(sys, 'PredefinedType', None)
                    } for sys in systems]
                except Exception as e:
                    element_data['systems'] = [{'error': str(e)}]
            
            # Get connections
            if include_connections:
                try:
                    if hasattr(element, 'ConnectedTo') and element.ConnectedTo:
                        for rel in element.ConnectedTo:
                            if hasattr(rel, 'RelatedElement'):
                                connected = rel.RelatedElement
                                element_data['connections']['to'].append({
                                    'name': connected.Name,
                                    'type': connected.is_a()
                                })
                    
                    if hasattr(element, 'ConnectedFrom') and element.ConnectedFrom:
                        for rel in element.ConnectedFrom:
                            if hasattr(rel, 'RelatingElement'):
                                connected = rel.RelatingElement
                                element_data['connections']['from'].append({
                                    'name': connected.Name,
                                    'type': connected.is_a()
                                })
                except Exception as e:
                    element_data['connections'] = {'error': str(e)}
            
            result['primary_equipment']['elements'].append(element_data)
        
        # 2. Analyze related equipment types
        if related_equipment_types:
            result['related_equipment'] = {}
            for eq_type in related_equipment_types:
                try:
                    related_elements = ifc_file.by_type(eq_type)
                    result['related_equipment'][eq_type] = {
                        'count': len(related_elements),
                        'sample_elements': []
                    }
                    
                    # Show first few elements as samples
                    for element in related_elements[:3]:
                        sample_data = {
                            'name': element.Name,
                            'object_type': getattr(element, 'ObjectType', None),
                            'predefined_type': getattr(element, 'PredefinedType', None)
                        }
                        result['related_equipment'][eq_type]['sample_elements'].append(sample_data)
                        
                except Exception as e:
                    result['related_equipment'][eq_type] = {'error': str(e)}
        
        # 3. System analysis
        if include_systems:
            try:
                all_systems = ifc_file.by_type('IfcSystem')
                relevant_systems = []
                
                for system in all_systems:
                    system_data = {
                        'name': system.Name,
                        'type': system.is_a(),
                        'object_type': getattr(system, 'ObjectType', None),
                        'predefined_type': getattr(system, 'PredefinedType', None)
                    }
                    
                    # Check if system contains our primary equipment
                    if hasattr(system, 'ServicesBuildings') or hasattr(system, 'HasAssignments'):
                        relevant_systems.append(system_data)
                
                result['systems'] = {
                    'total_systems': len(all_systems),
                    'relevant_systems': relevant_systems
                }
            except Exception as e:
                result['systems'] = {'error': str(e)}
        
    except Exception as e:
        result['error'] = str(e)
    
    # 4. Summary (always create this)
    result['summary'] = {
        'primary_equipment_count': len(primary_elements),
        'related_equipment_types_found': len(result['related_equipment']) if related_equipment_types else 0,
        'systems_analyzed': include_systems,
        'connections_analyzed': include_connections
    }
    
    return result