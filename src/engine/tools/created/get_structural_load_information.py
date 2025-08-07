
import ifcopenshell
from typing import Any, Dict, List, Optional
import ifcopenshell.util.element

def get_structural_load_information(
    ifc_file_path: str,
    element_type: Optional[str] = None,
    element_guid: Optional[str] = None,
    load_types: Optional[List[str]] = None,
    storey_name: Optional[str] = None,
    property_set_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Retrieve structural load information from IFC elements.
    
    This function searches for various types of structural load information including 
    live loads, dead loads, imposed loads, and load-bearing capacity. It works with 
    different structural element types and checks both direct attributes and property sets.
    
    Note: This function looks for properties in common structural property sets. For 
    software-specific properties (e.g., PSet_Revit_Dimensions), you may need to specify 
    those property set names explicitly.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_type (str, optional): Specific IFC element type to search within 
            (e.g., 'IfcSlab', 'IfcBeam')
        element_guid (str, optional): GlobalId of a specific element to query
        load_types (List[str], optional): Specific load types to search for 
            (e.g., ['LiveLoad', 'DeadLoad', 'ImposedLoad', 'LoadBearingCapacity'])
        storey_name (str, optional): Building storey name to filter elements
        property_set_names (List[str], optional): Specific property set names to search within
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'elements': List of dictionaries with element information and found load properties
            - 'summary': Summary of load information found
            - 'missing_data': Information about load data that was searched for but not found
            - 'recommendations': Suggestions for finding load information if not directly available
    """
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Initialize results
    elements_data = []
    summary = {}
    missing_data = []
    recommendations = []
    
    # Define common structural property sets if not provided
    if property_set_names is None:
        property_set_names = [
            'Pset_StructuralSurfaceMember',
            'Pset_StructuralSurfaceMemberVarying',
            'Pset_StructuralPlanarAction',
            'Pset_StructuralPlanarActionVarying',
            'Pset_StructuralElement',
            'Pset_SlabCommon',
            'Pset_BeamCommon',
            'Pset_ColumnCommon',
            'PSet_Revit_Structural',
            'PSet_Revit_Dimensions',
            'Pset_Revit_StructuralFoundation',
            'Pset_Revit_StructuralFraming',
            'Pset_Revit_StructuralAnalysis',
            'Pset_Revit_Loads',
            'Structural',
            'Loads',
            'Load',
            'Capacity'
        ]
    
    # Define common load types if not provided
    if load_types is None:
        load_types = ['LiveLoad', 'DeadLoad', 'ImposedLoad', 'LoadBearingCapacity', 'LoadBearing', 'Capacity', 'Load']
    
    # Get elements based on filters
    elements = []
    if element_guid:
        # Get specific element by GUID
        try:
            element = ifc_file.by_guid(element_guid)
            if element:
                elements = [element]
        except Exception as e:
            recommendations.append(f"Could not find element with GUID {element_guid}: {str(e)}")
    else:
        # Get elements by type or all structural elements
        if element_type:
            elements = ifc_file.by_type(element_type)
        else:
            # Get all structural elements
            structural_types = [
                'IfcStructuralSurfaceMember',
                'IfcStructuralCurveMember',
                'IfcSlab',
                'IfcBeam',
                'IfcColumn',
                'IfcFooting',
                'IfcPile',
                'IfcStructuralAnalysisModel'
            ]
            for struct_type in structural_types:
                elements.extend(ifc_file.by_type(struct_type))
    
    # Filter by storey if specified
    if storey_name:
        filtered_elements = []
        for element in elements:
            # Get the containing storey
            try:
                container = ifcopenshell.util.element.get_container(element)
                if container and container.is_a('IfcBuildingStorey'):
                    if storey_name.lower() in getattr(container, 'Name', '').lower():
                        filtered_elements.append(element)
            except Exception as e:
                recommendations.append(f"Could not determine container for element {element.GlobalId}: {str(e)}")
        elements = filtered_elements
    
    # Process each element
    load_info_found = {load_type: 0 for load_type in load_types}
    
    for element in elements:
        element_info = {
            'guid': element.GlobalId,
            'type': element.is_a(),
            'name': getattr(element, 'Name', 'N/A'),
            'load_properties': {},
            'is_heavy_equipment_reinforced': False
        }
        
        # Check direct attributes for load information (safely)
        try:
            # Use hasattr to check if the element has attribute_names method
            if hasattr(element, 'attribute_names'):
                for attr in element.attribute_names():
                    attr_value = getattr(element, attr, None)
                    # Look for load-related attributes
                    if attr_value is not None:
                        for load_type in load_types:
                            if load_type.lower() in attr.lower():
                                element_info['load_properties'][attr] = attr_value
                                load_info_found[load_type] += 1
            else:
                # Fallback: try to access common attributes directly
                common_attrs = ['PredefinedType', 'ObjectType', 'Description', 'Tag']
                for attr in common_attrs:
                    if hasattr(element, attr):
                        attr_value = getattr(element, attr, None)
                        if attr_value is not None:
                            for load_type in load_types:
                                if load_type.lower() in str(attr_value).lower():
                                    element_info['load_properties'][attr] = attr_value
                                    load_info_found[load_type] += 1
        except Exception as e:
            recommendations.append(f"Could not extract attributes for element {element.GlobalId}: {str(e)}")
        
        # Check property sets for load information
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            if psets:
                for pset_name, pset_data in psets.items():
                    # Check if this is a relevant property set (expanded criteria)
                    is_relevant_pset = (
                        any(name.lower() in pset_name.lower() for name in property_set_names) or
                        any(keyword in pset_name.lower() for keyword in ['load', 'capacity', 'bearing', 'structural', 'force']) or
                        'pset_' in pset_name.lower()
                    )
                    
                    if is_relevant_pset:
                        for prop_name, prop_value in pset_data.items():
                            # Look for load-related properties (expanded criteria)
                            is_load_related = (
                                any(load_type.lower() in prop_name.lower() for load_type in load_types) or
                                any(keyword in prop_name.lower() for keyword in ['load', 'capacity', 'bearing', 'stress', 'force', 'pressure', 'weight']) or
                                (isinstance(prop_value, (int, float)) and prop_value > 0)
                            )
                            
                            if is_load_related and prop_value:
                                element_info['load_properties'][f"{pset_name}.{prop_name}"] = prop_value
                                # Count this as a matching load type or add a generic one
                                matched_load_type = None
                                for load_type in load_types:
                                    if load_type.lower() in prop_name.lower():
                                        matched_load_type = load_type
                                        break
                                
                                if matched_load_type:
                                    load_info_found[matched_load_type] += 1
                                else:
                                    # Add a generic counter for load-related properties
                                    if 'LoadRelated' not in load_info_found:
                                        load_info_found['LoadRelated'] = 0
                                    load_info_found['LoadRelated'] += 1
                            
                            # Check for heavy equipment reinforcement indicators
                            # This addresses the original issue - we need to be more specific
                            # about what indicates reinforcement for heavy equipment
                            heavy_equipment_indicators = [
                                'heavyequipment', 'heavy_equipment', 'medicalequipment', 
                                'medical_equipment', 'reinforced', 'thickened', 'enhanced',
                                'equipmentload', 'equipment_load', 'pointload', 'point_load',
                                'concentrated', 'distributed', 'machinery', 'vibration',
                                'dynamic', 'impact', 'shock'
                            ]
                            
                            # Additional check for values that might indicate heavy equipment reinforcement
                            capacity_indicators = ['load', 'capacity', 'bearing', 'strength', 'force', 'stress']
                            
                            # Check property name for indicators
                            if any(indicator in prop_name.lower() for indicator in heavy_equipment_indicators):
                                if any(capacity in prop_name.lower() for capacity in capacity_indicators):
                                    element_info['is_heavy_equipment_reinforced'] = True
                            
                            # Also check the property value for indicators
                            if isinstance(prop_value, str):
                                if any(indicator in prop_value.lower() for indicator in heavy_equipment_indicators):
                                    element_info['is_heavy_equipment_reinforced'] = True
        except Exception as e:
            # Handle cases where property set extraction fails
            recommendations.append(f"Could not extract properties for element {element.GlobalId}: {str(e)}")
        
        # Only add elements that have load information or are specifically requested
        if element_info['load_properties'] or element_guid or element_type:
            elements_data.append(element_info)
    
    # Create summary
    summary = {
        'total_elements_processed': len(elements_data),
        'load_types_found': {k: v for k, v in load_info_found.items() if v > 0},
        'elements_with_heavy_equipment_reinforcement': sum(1 for e in elements_data if e.get('is_heavy_equipment_reinforced', False))
    }
    
    # Identify missing data
    for load_type, count in load_info_found.items():
        if count == 0:
            missing_data.append(f"No {load_type} information found")
    
    # Add recommendations
    if not elements_data:
        recommendations.append("No structural elements with load information found. Consider checking property set names or load types.")
    
    if not any(count > 0 for count in load_info_found.values()):
        recommendations.append("No load information found. Try expanding the search with different property set names or load types.")
        recommendations.append("Consider checking for software-specific property sets like 'PSet_Revit_Structural' or 'PSet_Revit_Dimensions'.")
    
    return {
        'elements': elements_data,
        'summary': summary,
        'missing_data': missing_data,
        'recommendations': recommendations
    }
