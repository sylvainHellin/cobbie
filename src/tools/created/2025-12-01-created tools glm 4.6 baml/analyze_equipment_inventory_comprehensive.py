import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_equipment_inventory_comprehensive(
    ifc_file,
    primary_equipment_types: List[str] = ['IfcUnitaryEquipment', 'IfcBoiler', 'IfcChiller', 'IfcHeatPump', 'IfcFlowMovingDevice', 'IfcPump', 'IfcPumpType'],
    related_equipment_types: List[str] = ['IfcAirTerminal', 'IfcCoil', 'IfcFan', 'IfcHeatExchanger'],
    mechanical_equipment_types: Optional[List[str]] = None,
    include_property_extraction: bool = True,
    max_examples_per_type: int = 5,
    include_summary: bool = True
) -> Dict[str, Any]:
    """
    Analyzes equipment inventory in an IFC model by discovering unitary equipment and related systems.
    
    This function implements a systematic workflow for equipment inventory analysis:
    1) Queries primary equipment types (IfcUnitaryEquipment, IfcBoiler, etc.)
    2) Checks for related equipment types that might be part of unitary systems
    3) Extracts properties using multiple fallback strategies
    4) Provides categorized results with counts and details
    5) Enhanced with pump and mechanical equipment analysis
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        primary_equipment_types: List of primary equipment types to analyze
        related_equipment_types: List of related equipment types to check
        mechanical_equipment_types: Optional list of mechanical equipment types (pumps, valves, etc.)
        include_property_extraction: Boolean to attempt detailed property extraction
        max_examples_per_type: Maximum number of examples to show per equipment type
        include_summary: Boolean to include summary statistics
    
    Returns:
        Dict containing:
        - primary_equipment: Dict with equipment types as keys, each containing count and list of equipment details
        - related_equipment: Dict with related equipment types and their counts
        - mechanical_equipment: Dict with mechanical equipment types and their details (if provided)
        - summary: Overall statistics and totals
        - property_extraction_status: Information about property extraction success
        - schema_info: Schema version and compatibility information
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_equipment_inventory_comprehensive(model)
        >>> print(f"Found {result['summary']['total_primary_equipment']} primary equipment items")
    """
    result = {
        'primary_equipment': {},
        'related_equipment': {},
        'mechanical_equipment': {},
        'summary': {},
        'property_extraction_status': {'success_count': 0, 'failed_count': 0, 'errors': []},
        'schema_info': {'schema_version': str(ifc_file.schema)}
    }
    
    # Set default mechanical equipment types if not provided
    if mechanical_equipment_types is None:
        mechanical_equipment_types = ['IfcFlowMovingDevice', 'IfcPump', 'IfcPumpType', 'IfcValve', 'IfcFlowController']
    
    def extract_enhanced_properties(element):
        """Extract properties with enhanced focus on manufacturer and electrical info"""
        properties = {}
        try:
            # Try utility function first
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Extract key property sets for equipment analysis
            key_psets = ['Pset_ManufacturerTypeInformation', 'Pset_ElectricalDeviceCommon', 
                        'Pset_DistributionFlowElementCommon', 'Pset_ProductRequirements', 'Pset_QuantityTakeOff']
            
            for pset_name in key_psets:
                if pset_name in psets:
                    properties[pset_name] = psets[pset_name]
            
            # Include all other properties
            for pset_name, pset_data in psets.items():
                if pset_name not in properties:
                    properties[pset_name] = pset_data
                    
            result['property_extraction_status']['success_count'] += 1
            return properties
            
        except Exception as prop_error:
            # Fallback: manual property extraction
            try:
                manual_props = {}
                if hasattr(element, 'IsDefinedBy') and element.IsDefinedBy:
                    for relationship in element.IsDefinedBy:
                        if hasattr(relationship, 'RelatingPropertyDefinition'):
                            prop_def = relationship.RelatingPropertyDefinition
                            if hasattr(prop_def, 'Name') and hasattr(prop_def, 'HasProperties'):
                                prop_set_name = prop_def.Name
                                manual_props[prop_set_name] = {}
                                for prop in prop_def.HasProperties:
                                    if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                        value = prop.NominalValue.wrappedValue if prop.NominalValue else None
                                        manual_props[prop_set_name][prop.Name] = value
                
                if manual_props:
                    result['property_extraction_status']['success_count'] += 1
                    return manual_props
                else:
                    result['property_extraction_status']['failed_count'] += 1
                    return {'error': 'No properties found'}
                    
            except Exception as fallback_error:
                result['property_extraction_status']['failed_count'] += 1
                result['property_extraction_status']['errors'].append(
                    f"Property extraction failed for {element.GlobalId}: {str(fallback_error)}"
                )
                return {'error': f'Property extraction failed: {str(fallback_error)}'}
    
    def extract_type_relationships(element):
        """Extract type relationship information for equipment classification"""
        type_info = {}
        try:
            if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
                for rel in element.IsTypedBy:
                    if hasattr(rel, 'RelatingType'):
                        type_element = rel.RelatingType
                        type_info = {
                            'type_globalid': type_element.GlobalId,
                            'type_name': type_element.Name,
                            'type_objecttype': getattr(type_element, 'ObjectType', None),
                            'type_predefinedtype': getattr(type_element, 'PredefinedType', None)
                        }
                        break  # Take the first type relationship
            return type_info
        except Exception as e:
            return {'error': f'Type relationship extraction failed: {str(e)}'}
    
    def analyze_equipment_type(eq_type, category='primary'):
        """Analyze a specific equipment type with schema compatibility fallback"""
        try:
            # Schema compatibility check - some types may not exist in older schemas
            elements = ifc_file.by_type(eq_type)
            equipment_details = []
            
            for i, element in enumerate(elements[:max_examples_per_type]):
                detail = {
                    'GlobalId': element.GlobalId,
                    'Name': element.Name or 'Unnamed',
                    'ObjectType': getattr(element, 'ObjectType', None),
                    'PredefinedType': getattr(element, 'PredefinedType', None)
                }
                
                # Add type relationship information
                type_info = extract_type_relationships(element)
                if type_info:
                    detail['type_relationship'] = type_info
                
                # Extract enhanced properties if requested
                if include_property_extraction:
                    detail['properties'] = extract_enhanced_properties(element)
                
                equipment_details.append(detail)
            
            return {
                'count': len(elements),
                'examples': equipment_details
            }
            
        except Exception as e:
            error_msg = str(e)
            # Check if it's a schema compatibility issue
            if 'not found in schema' in error_msg:
                error_msg = f"Type not available in {ifc_file.schema} schema"
            
            return {
                'count': 0,
                'examples': [],
                'error': error_msg
            }
    
    # Analyze primary equipment types
    for eq_type in primary_equipment_types:
        result['primary_equipment'][eq_type] = analyze_equipment_type(eq_type, 'primary')
        if 'error' in result['primary_equipment'][eq_type]:
            result['property_extraction_status']['errors'].append(f"Primary {eq_type}: {result['primary_equipment'][eq_type]['error']}")
    
    # Analyze related equipment types
    for eq_type in related_equipment_types:
        result['related_equipment'][eq_type] = analyze_equipment_type(eq_type, 'related')
        if 'error' in result['related_equipment'][eq_type]:
            result['property_extraction_status']['errors'].append(f"Related {eq_type}: {result['related_equipment'][eq_type]['error']}")
    
    # Analyze mechanical equipment types
    for eq_type in mechanical_equipment_types:
        result['mechanical_equipment'][eq_type] = analyze_equipment_type(eq_type, 'mechanical')
        if 'error' in result['mechanical_equipment'][eq_type]:
            result['property_extraction_status']['errors'].append(f"Mechanical {eq_type}: {result['mechanical_equipment'][eq_type]['error']}")
    
    # Generate summary
    if include_summary:
        total_primary = sum(data['count'] for data in result['primary_equipment'].values() if isinstance(data, dict) and 'count' in data)
        total_related = sum(data['count'] for data in result['related_equipment'].values() if isinstance(data, dict) and 'count' in data)
        total_mechanical = sum(data['count'] for data in result['mechanical_equipment'].values() if isinstance(data, dict) and 'count' in data)
        
        result['summary'] = {
            'total_primary_equipment': total_primary,
            'total_related_equipment': total_related,
            'total_mechanical_equipment': total_mechanical,
            'total_equipment': total_primary + total_related + total_mechanical,
            'primary_types_found': [eq_type for eq_type, data in result['primary_equipment'].items() 
                                   if isinstance(data, dict) and data.get('count', 0) > 0],
            'related_types_found': [eq_type for eq_type, data in result['related_equipment'].items() 
                                  if isinstance(data, dict) and data.get('count', 0) > 0],
            'mechanical_types_found': [eq_type for eq_type, data in result['mechanical_equipment'].items() 
                                     if isinstance(data, dict) and data.get('count', 0) > 0]
        }
    
    return result