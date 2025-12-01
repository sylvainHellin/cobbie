import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def analyze_load_bearing_elements(
    ifc_file,
    element_type: str,
    load_bearing_properties: List[str] = ['LoadBearing', 'Structural Usage'],
    structural_usage_values: Dict[str, bool] = {'Non-bearing': False, 'Load-bearing': True, 'Bearing': True},
    categorize_by: str = 'ObjectType',
    include_details: bool = False,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes load-bearing characteristics of IFC elements by examining their property sets.
    
    This function determines which structural elements are load-bearing vs non-load-bearing
    by examining property sets and provides comprehensive breakdowns by element type.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcColumn', 'IfcBeam')
        load_bearing_properties: List of property names that indicate load-bearing status
        structural_usage_values: Dict mapping structural usage values to boolean load-bearing status
        categorize_by: Field to categorize elements by ('ObjectType', 'Name', 'PredefinedType')
        include_details: Boolean to include detailed element information
        case_sensitive: Boolean for case-sensitive property matching
    
    Returns:
        Dict containing:
        - total_count: Total number of elements analyzed
        - load_bearing_count: Number of load-bearing elements
        - non_load_bearing_count: Number of non-load-bearing elements
        - load_bearing_percentage: Percentage of load-bearing elements
        - breakdown_by_type: Dict with counts and percentages for each element type
        - load_bearing_by_type: Dict showing load-bearing counts by type
        - details: Optional detailed element information (if include_details=True)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_load_bearing_elements(model, 'IfcWall')
        >>> print(f"Load-bearing walls: {result['load_bearing_count']}/{result['total_count']}")
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_count = len(elements)
        
        if total_count == 0:
            return {
                'total_count': 0,
                'load_bearing_count': 0,
                'non_load_bearing_count': 0,
                'load_bearing_percentage': 0.0,
                'breakdown_by_type': {},
                'load_bearing_by_type': {},
                'details': [] if include_details else None
            }
        
        load_bearing_elements = []
        non_load_bearing_elements = []
        breakdown_by_type = {}
        load_bearing_by_type = {}
        details = [] if include_details else None
        
        # Helper function to get attribute value safely
        def get_attribute_value(element, attr_name: str) -> str:
            value = getattr(element, attr_name, None)
            return str(value) if value is not None else 'Unknown'
        
        # Helper function for case-insensitive string comparison
        def normalize_string(s: str) -> str:
            return s if case_sensitive else s.lower()
        
        for element in elements:
            # Get categorization value
            category = get_attribute_value(element, categorize_by)
            
            # Count by type
            if category not in breakdown_by_type:
                breakdown_by_type[category] = 0
            breakdown_by_type[category] += 1
            
            # Determine load-bearing status
            is_load_bearing = False
            load_bearing_source = None
            
            try:
                # Get property sets using ifcopenshell utility
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Check for load-bearing properties
                for prop_name in load_bearing_properties:
                    prop_name_normalized = normalize_string(prop_name)
                    
                    # Search in all property sets
                    for pset_name, pset_data in psets.items():
                        for pset_prop_name, pset_prop_value in pset_data.items():
                            pset_prop_name_normalized = normalize_string(pset_prop_name)
                            
                            if pset_prop_name_normalized == prop_name_normalized:
                                if prop_name == 'LoadBearing' and isinstance(pset_prop_value, bool):
                                    is_load_bearing = pset_prop_value
                                    load_bearing_source = f'{pset_name}.{pset_prop_name}'
                                    break
                                elif prop_name == 'Structural Usage' and isinstance(pset_prop_value, str):
                                    usage_normalized = normalize_string(pset_prop_value)
                                    for usage_key, usage_value in structural_usage_values.items():
                                        if normalize_string(usage_key) == usage_normalized:
                                            is_load_bearing = usage_value
                                            load_bearing_source = f'{pset_name}.{pset_prop_name}'
                                            break
                            if load_bearing_source:
                                break
                        if load_bearing_source:
                            break
                    if load_bearing_source:
                        break
                        
            except Exception as e:
                # Fallback to manual property access if utility fails
                try:
                    for definition in element.IsDefinedBy:
                        if definition.is_a('IfcRelDefinesByProperties'):
                            property_set = definition.RelatingPropertyDefinition
                            if property_set.is_a('IfcPropertySet'):
                                for prop in property_set.HasProperties:
                                    if hasattr(prop, 'NominalValue'):
                                        prop_name = prop.Name
                                        prop_name_normalized = normalize_string(prop_name)
                                        
                                        for load_prop in load_bearing_properties:
                                            load_prop_normalized = normalize_string(load_prop)
                                            
                                            if prop_name_normalized == load_prop_normalized:
                                                prop_value = prop.NominalValue.wrappedValue
                                                
                                                if load_prop == 'LoadBearing' and isinstance(prop_value, bool):
                                                    is_load_bearing = prop_value
                                                    load_bearing_source = f'{property_set.Name}.{prop_name}'
                                                    break
                                                elif load_prop == 'Structural Usage' and isinstance(prop_value, str):
                                                    usage_normalized = normalize_string(prop_value)
                                                    for usage_key, usage_value in structural_usage_values.items():
                                                        if normalize_string(usage_key) == usage_normalized:
                                                            is_load_bearing = usage_value
                                                            load_bearing_source = f'{property_set.Name}.{prop_name}'
                                                            break
                                        if load_bearing_source:
                                            break
                                if load_bearing_source:
                                    break
                except Exception:
                    # If all property access fails, assume non-load-bearing
                    is_load_bearing = False
            
            # Categorize element
            if is_load_bearing:
                load_bearing_elements.append(element)
                if category not in load_bearing_by_type:
                    load_bearing_by_type[category] = 0
                load_bearing_by_type[category] += 1
            else:
                non_load_bearing_elements.append(element)
            
            # Add details if requested
            if include_details and details is not None:
                element_detail = {
                    'id': element.id(),
                    'GlobalId': element.GlobalId,
                    'Name': element.Name,
                    'ObjectType': element.ObjectType,
                    'PredefinedType': getattr(element, 'PredefinedType', None),
                    'category': category,
                    'is_load_bearing': is_load_bearing,
                    'load_bearing_source': load_bearing_source
                }
                details.append(element_detail)
        
        # Calculate percentages
        load_bearing_count = len(load_bearing_elements)
        non_load_bearing_count = len(non_load_bearing_elements)
        load_bearing_percentage = (load_bearing_count / total_count * 100) if total_count > 0 else 0.0
        
        # Enhance breakdown with percentages
        enhanced_breakdown = {}
        for category, count in breakdown_by_type.items():
            load_bearing_count_for_type = load_bearing_by_type.get(category, 0)
            enhanced_breakdown[category] = {
                'total_count': count,
                'load_bearing_count': load_bearing_count_for_type,
                'load_bearing_percentage': (load_bearing_count_for_type / count * 100) if count > 0 else 0.0
            }
        
        return {
            'total_count': total_count,
            'load_bearing_count': load_bearing_count,
            'non_load_bearing_count': non_load_bearing_count,
            'load_bearing_percentage': round(load_bearing_percentage, 1),
            'breakdown_by_type': enhanced_breakdown,
            'load_bearing_by_type': load_bearing_by_type,
            'details': details
        }
        
    except Exception as e:
        return {
            'total_count': 0,
            'load_bearing_count': 0,
            'non_load_bearing_count': 0,
            'load_bearing_percentage': 0.0,
            'breakdown_by_type': {},
            'load_bearing_by_type': {},
            'details': [],
            'error': str(e)
        }