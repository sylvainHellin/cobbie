import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional
from collections import defaultdict

def infer_contained_hvac_components(
    ifc_file: ifcopenshell.file,
    target_components: List[str],
    equipment_keywords: Optional[List[str]] = None,
    property_keywords: Optional[Dict[str, List[str]]] = None,
    include_equipment_details: bool = True,
    confidence_threshold: float = 0.7,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Infers the presence and types of contained HVAC components within larger equipment units
    by analyzing equipment types, properties, and naming patterns.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        target_components: List of component types to infer (e.g., ['coil', 'compressor', 'fan', 'pump'])
        equipment_keywords: Optional list of equipment type keywords to search
        property_keywords: Optional dict mapping component types to property keywords for inference
        include_equipment_details: Whether to include detailed equipment information (default True)
        confidence_threshold: Minimum confidence level for component inference (0-1, default 0.7)
        case_sensitive: Whether keyword matching should be case sensitive (default False)
    
    Returns:
        Dict containing:
        - found_equipment: List of equipment units that likely contain target components
        - inferred_components: Dict mapping component types to equipment that contains them
        - confidence_scores: Confidence levels for each inference
        - equipment_details: Detailed properties of found equipment
        - summary: Overall statistics and recommendations
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = infer_contained_hvac_components(
        ...     model,
        ...     target_components=['coil', 'compressor', 'fan'],
        ...     confidence_threshold=0.6
        ... )
        >>> print(f"Found {len(result['found_equipment'])} equipment units")
        >>> for component_type, components in result['inferred_components'].items():
        ...     print(f"{component_type}: {len(components)} instances")
    """
    
    # Default equipment keywords if not provided
    if equipment_keywords is None:
        equipment_keywords = [
            'CHILLER', 'AHU', 'AIR HANDLER', 'AIRHANDLER', 'FAN COIL', 'FANCOIL',
            'HEAT EXCHANGER', 'HEATEXCHANGER', 'HX', 'CONDENSING UNIT', 'CONDENSINGUNIT',
            'BOILER', 'ROOFTOP UNIT', 'RTU', 'MAKEUP AIR UNIT', 'MAU', 'COOLING TOWER',
            'VAV', 'AIR CONDITIONER', 'AC UNIT', 'REFRIGERATION', 'HEATING UNIT'
        ]
    
    # Default property keywords for component inference if not provided
    if property_keywords is None:
        property_keywords = {
            'coil': ['COIL', 'EVAPORATOR', 'CONDENSER', 'COOLING COIL', 'HEATING COIL', 'REFRIGERANT', 'DX COIL', 'WATER COIL'],
            'compressor': ['COMPRESSOR', 'SCREW', 'CENTRIFUGAL', 'RECIPROCATING', 'SCROLL'],
            'fan': ['FAN', 'BLOWER', 'AIRFLOW', 'CFM', 'STATIC PRESSURE'],
            'pump': ['PUMP', 'CIRCULATOR', 'FLOW RATE', 'HEAD', 'GPM']
        }
    
    try:
        # Initialize result structure
        result = {
            'found_equipment': [],
            'inferred_components': defaultdict(list),
            'confidence_scores': defaultdict(dict),
            'equipment_details': {},
            'summary': {
                'total_equipment_searched': 0,
                'equipment_with_inferred_components': 0,
                'components_inferred': defaultdict(int),
                'recommendations': []
            }
        }
        
        # Equipment types to search for HVAC equipment
        equipment_types = [
            'IfcEnergyConversionDevice',
            'IfcDistributionElement', 
            'IfcDistributionFlowElement',
            'IfcFlowMovingDevice',
            'IfcFlowController',
            'IfcFlowTerminal',
            'IfcBuildingElementProxy'
        ]
        
        # Use a set to track processed element IDs to avoid duplicates
        processed_element_ids = set()
        
        # Search for HVAC equipment
        found_equipment = []
        for eq_type in equipment_types:
            try:
                elements = ifc_file.by_type(eq_type)
                for element in elements:
                    # Skip if already processed
                    if element.id() in processed_element_ids:
                        continue
                    
                    processed_element_ids.add(element.id())
                    result['summary']['total_equipment_searched'] += 1
                    
                    # Check if element matches equipment keywords
                    name_match = False
                    object_type_match = False
                    
                    element_name = element.Name or ''
                    element_object_type = element.ObjectType or ''
                    
                    if not case_sensitive:
                        element_name = element_name.upper()
                        element_object_type = element_object_type.upper()
                    
                    for keyword in equipment_keywords:
                        search_keyword = keyword if case_sensitive else keyword.upper()
                        if search_keyword in element_name:
                            name_match = True
                        if search_keyword in element_object_type:
                            object_type_match = True
                    
                    if name_match or object_type_match:
                        equipment_info = {
                            'id': element.id(),
                            'global_id': element.GlobalId,
                            'name': element.Name,
                            'object_type': element.ObjectType,
                            'type': element.is_a(),
                            'matched_fields': [],
                            'container': None
                        }
                        
                        if name_match:
                            equipment_info['matched_fields'].append('Name')
                        if object_type_match:
                            equipment_info['matched_fields'].append('ObjectType')
                        
                        # Get spatial container
                        try:
                            container = ifcopenshell.util.element.get_container(element)
                            if container:
                                equipment_info['container'] = {
                                    'name': container.Name,
                                    'type': container.is_a(),
                                    'id': container.id()
                                }
                        except:
                            pass
                        
                        found_equipment.append(equipment_info)
            except Exception:
                continue
        
        result['found_equipment'] = found_equipment
        
        # Analyze each equipment for inferred components
        for equipment in found_equipment:
            try:
                element = ifc_file.by_id(equipment['id'])
                
                # Get property sets for detailed analysis
                psets = {}
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                except:
                    pass
                
                # Also get type properties if available
                type_psets = {}
                try:
                    element_type = ifcopenshell.util.element.get_type(element)
                    if element_type:
                        type_psets = ifcopenshell.util.element.get_psets(element_type)
                except:
                    pass
                
                # Combine all properties for analysis
                all_properties = {**psets, **type_psets}
                
                # Store equipment details if requested
                if include_equipment_details:
                    result['equipment_details'][equipment['id']] = {
                        'name': equipment['name'],
                        'object_type': equipment['object_type'],
                        'type': equipment['type'],
                        'property_sets': all_properties,
                        'container': equipment['container']
                    }
                
                # Infer components based on equipment type and properties
                inferred_for_equipment = []
                
                for component_type in target_components:
                    confidence = 0.0
                    inference_reasons = []
                    
                    # Check equipment name and type for component indicators
                    equipment_text = f"{equipment['name']} {equipment['object_type']}".upper()
                    
                    if component_type in property_keywords:
                        for keyword in property_keywords[component_type]:
                            search_keyword = keyword.upper()
                            if search_keyword in equipment_text:
                                confidence += 0.3
                                inference_reasons.append(f"Keyword '{keyword}' found in equipment name/type")
                    
                    # Check properties for component indicators
                    for pset_name, pset_data in all_properties.items():
                        if isinstance(pset_data, dict):
                            for prop_name, prop_value in pset_data.items():
                                if isinstance(prop_value, str):
                                    prop_text = prop_value.upper()
                                    if component_type in property_keywords:
                                        for keyword in property_keywords[component_type]:
                                            search_keyword = keyword.upper()
                                            if search_keyword in prop_text:
                                                confidence += 0.2
                                                inference_reasons.append(f"Keyword '{keyword}' found in property {prop_name}")
                    
                    # Equipment-specific inference rules
                    equipment_name_upper = equipment['name'].upper() if equipment['name'] else ''
                    
                    if component_type == 'coil':
                        if 'CHILLER' in equipment_name_upper:
                            confidence += 0.4
                            inference_reasons.append('Chillers typically contain evaporator and condenser coils')
                        elif 'AHU' in equipment_name_upper or 'AIR HANDLER' in equipment_name_upper:
                            confidence += 0.4
                            inference_reasons.append('Air handlers typically contain heating and cooling coils')
                        elif 'FAN COIL' in equipment_name_upper:
                            confidence += 0.5
                            inference_reasons.append('Fan coil units contain coils by definition')
                    
                    elif component_type == 'compressor':
                        if 'CHILLER' in equipment_name_upper:
                            confidence += 0.4
                            inference_reasons.append('Chillers contain compressors')
                        elif 'REFRIGERATION' in equipment_name_upper:
                            confidence += 0.4
                            inference_reasons.append('Refrigeration equipment contains compressors')
                    
                    elif component_type == 'fan':
                        if 'AHU' in equipment_name_upper or 'AIR HANDLER' in equipment_name_upper:
                            confidence += 0.4
                            inference_reasons.append('Air handlers contain fans')
                        elif 'FAN COIL' in equipment_name_upper:
                            confidence += 0.5
                            inference_reasons.append('Fan coil units contain fans by definition')
                        elif 'RTU' in equipment_name_upper or 'ROOFTOP' in equipment_name_upper:
                            confidence += 0.3
                            inference_reasons.append('Rooftop units typically contain fans')
                    
                    elif component_type == 'pump':
                        if 'CHILLER' in equipment_name_upper:
                            confidence += 0.3
                            inference_reasons.append('Chillers typically have condenser water pumps')
                        elif 'BOILER' in equipment_name_upper:
                            confidence += 0.4
                            inference_reasons.append('Boilers typically have circulation pumps')
                    
                    # Apply confidence threshold
                    if confidence >= confidence_threshold:
                        result['inferred_components'][component_type].append({
                            'equipment_id': equipment['id'],
                            'equipment_name': equipment['name'],
                            'equipment_type': equipment['type'],
                            'confidence': min(confidence, 1.0),
                            'reasons': inference_reasons
                        })
                        result['confidence_scores'][component_type][equipment['id']] = min(confidence, 1.0)
                        inferred_for_equipment.append(component_type)
                        result['summary']['components_inferred'][component_type] += 1
                
                if inferred_for_equipment:
                    result['summary']['equipment_with_inferred_components'] += 1
                    
            except Exception:
                continue
        
        # Generate recommendations
        if result['summary']['equipment_with_inferred_components'] == 0:
            result['summary']['recommendations'].append(
                'No HVAC equipment with inferred components found. Consider expanding equipment keywords or lowering confidence threshold.'
            )
        else:
            result['summary']['recommendations'].append(
                f'Found {result["summary"]["equipment_with_inferred_components"]} equipment units with inferred components.'
            )
            
            for component_type, count in result['summary']['components_inferred'].items():
                if count > 0:
                    result['summary']['recommendations'].append(
                        f'Inferred {count} instances of {component_type} components.'
                    )
        
        return result
        
    except Exception as e:
        return {
            'error': f'Error in infer_contained_hvac_components: {str(e)}',
            'found_equipment': [],
            'inferred_components': {},
            'confidence_scores': {},
            'equipment_details': {},
            'summary': {'error': str(e)}
        }