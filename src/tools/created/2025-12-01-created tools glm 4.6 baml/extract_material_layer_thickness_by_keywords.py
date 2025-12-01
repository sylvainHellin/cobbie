import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def extract_material_layer_thickness_by_keywords(
    ifc_file,
    element_types: List[str],
    material_keywords: List[str],
    element_filter_keywords: Optional[List[str]] = None,
    element_filter_fields: List[str] = ['Name', 'ObjectType'],
    include_property_filtering: bool = True,
    aggregation_field: str = 'ObjectType',
    case_sensitive: bool = False,
    include_layer_details: bool = True,
    max_examples_per_type: int = 3
) -> Dict[str, Any]:
    """
    Extracts and analyzes material layer thickness from IFC elements using keyword-based material filtering.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element types to analyze (e.g., ['IfcWall', 'IfcSlab'])
        material_keywords: List of keywords to identify target materials (e.g., ['insul', 'thermal', 'waterproof'])
        element_filter_keywords: Optional list to filter elements (e.g., ['Exterior', 'External'])
        element_filter_fields: Fields to search for element filter keywords (default: ['Name', 'ObjectType'])
        include_property_filtering: Boolean to also filter by element properties like 'IsExternal' (default: True)
        aggregation_field: Field to group results by (default: 'ObjectType')
        case_sensitive: Boolean for keyword matching (default: False)
        include_layer_details: Boolean to include all layer information (default: True)
        max_examples_per_type: Maximum examples to show per element type (default: 3)
    
    Returns:
        Dict containing:
        - 'summary': Overall statistics (total elements, elements with target layers, etc.)
        - 'by_type': Results grouped by element type with thickness data
        - 'layer_details': Detailed information about found material layers
        - 'elements_analyzed': Count of elements processed
        - 'target_layers_found': Count of elements containing target material layers
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = extract_material_layer_thickness_by_keywords(
        ...     ifc_file,
        ...     element_types=['IfcWall'],
        ...     material_keywords=['insul', 'thermal'],
        ...     element_filter_keywords=['Exterior']
        ... )
        >>> print(result['summary'])
    """
    try:
        # Initialize result structure
        result = {
            'summary': {},
            'by_type': {},
            'layer_details': [],
            'elements_analyzed': 0,
            'target_layers_found': 0
        }
        
        # Prepare keywords for matching
        if not case_sensitive:
            material_keywords = [kw.lower() for kw in material_keywords]
            if element_filter_keywords:
                element_filter_keywords = [kw.lower() for kw in element_filter_keywords]
        
        # Collect all elements of specified types
        all_elements = []
        for element_type in element_types:
            elements = ifc_file.by_type(element_type)
            all_elements.extend(elements)
        
        result['elements_analyzed'] = len(all_elements)
        
        # Filter elements based on keywords and properties
        filtered_elements = []
        for element in all_elements:
            include_element = True
            
            # Apply element filter keywords if specified
            if element_filter_keywords:
                include_element = False
                for field in element_filter_fields:
                    field_value = getattr(element, field, None)
                    if field_value:
                        search_value = field_value if case_sensitive else field_value.lower()
                        for keyword in element_filter_keywords:
                            search_keyword = keyword if case_sensitive else keyword.lower()
                            if search_keyword in search_value:
                                include_element = True
                                break
                    if include_element:
                        break
            
            # Apply property filtering if enabled
            if include_element and include_property_filtering:
                # Check for IsExternal property if looking for external elements
                if element_filter_keywords and any('exterior' in kw.lower() or 'external' in kw.lower() for kw in element_filter_keywords):
                    is_external = False
                    if element.IsDefinedBy:
                        for rel in element.IsDefinedBy:
                            if hasattr(rel, 'RelatingPropertyDefinition'):
                                prop_def = rel.RelatingPropertyDefinition
                                if hasattr(prop_def, 'HasProperties'):
                                    for prop in prop_def.HasProperties:
                                        if hasattr(prop, 'Name') and prop.Name == 'IsExternal':
                                            if hasattr(prop, 'NominalValue') and prop.NominalValue.wrappedValue == True:
                                                is_external = True
                    include_element = is_external
            
            if include_element:
                filtered_elements.append(element)
        
        # Analyze material layers for filtered elements
        target_layers_data = []
        
        for element in filtered_elements:
            element_type_value = getattr(element, aggregation_field, None) or element.is_a()
            
            # Check material associations
            if element.HasAssociations:
                for assoc in element.HasAssociations:
                    if hasattr(assoc, 'RelatingMaterial'):
                        material = assoc.RelatingMaterial
                        
                        # Handle different material types
                        layers_to_check = []
                        
                        if material.is_a('IfcMaterialLayerSetUsage'):
                            layers_to_check = material.ForLayerSet.MaterialLayers
                        elif material.is_a('IfcMaterialLayerSet'):
                            layers_to_check = material.MaterialLayers
                        
                        # Check each layer for target keywords
                        for layer in layers_to_check:
                            if layer.Material and layer.Material.Name:
                                material_name = layer.Material.Name
                                search_name = material_name if case_sensitive else material_name.lower()
                                
                                # Check if material matches any target keywords
                                matches_keyword = False
                                for keyword in material_keywords:
                                    search_keyword = keyword if case_sensitive else keyword.lower()
                                    if search_keyword in search_name:
                                        matches_keyword = True
                                        break
                                
                                if matches_keyword:
                                    layer_data = {
                                        'element_id': element.GlobalId,
                                        'element_type': element.is_a(),
                                        'aggregation_value': element_type_value,
                                        'material_name': material_name,
                                        'thickness': layer.LayerThickness,
                                        'layer_index': layers_to_check.index(layer)
                                    }
                                    
                                    if include_layer_details:
                                        layer_data['total_layers'] = len(layers_to_check)
                                        layer_data['all_layers'] = []
                                        for i, l in enumerate(layers_to_check):
                                            layer_info = {
                                                'index': i,
                                                'material_name': l.Material.Name if l.Material else 'Unknown',
                                                'thickness': l.LayerThickness
                                            }
                                            layer_data['all_layers'].append(layer_info)
                                    
                                    target_layers_data.append(layer_data)
                                    result['target_layers_found'] += 1
        
        # Group results by aggregation field
        by_type = {}
        for layer_data in target_layers_data:
            agg_value = layer_data['aggregation_value']
            
            if agg_value not in by_type:
                by_type[agg_value] = {
                    'thicknesses': [],
                    'materials': set(),
                    'element_count': 0,
                    'examples': []
                }
            
            by_type[agg_value]['thicknesses'].append(layer_data['thickness'])
            by_type[agg_value]['materials'].add(layer_data['material_name'])
            by_type[agg_value]['element_count'] += 1
            
            # Add examples (limited by max_examples_per_type)
            if len(by_type[agg_value]['examples']) < max_examples_per_type:
                example_data = {
                    'element_id': layer_data['element_id'],
                    'material_name': layer_data['material_name'],
                    'thickness': layer_data['thickness']
                }
                if include_layer_details and 'all_layers' in layer_data:
                    example_data['all_layers'] = layer_data['all_layers']
                by_type[agg_value]['examples'].append(example_data)
        
        # Convert sets to lists and calculate statistics
        for agg_value in by_type:
            by_type[agg_value]['materials'] = list(by_type[agg_value]['materials'])
            thicknesses = by_type[agg_value]['thicknesses']
            by_type[agg_value]['unique_thicknesses'] = list(set(thicknesses))
            by_type[agg_value]['min_thickness'] = min(thicknesses) if thicknesses else None
            by_type[agg_value]['max_thickness'] = max(thicknesses) if thicknesses else None
            by_type[agg_value]['avg_thickness'] = sum(thicknesses) / len(thicknesses) if thicknesses else None
        
        result['by_type'] = by_type
        result['layer_details'] = target_layers_data
        
        # Create summary
        result['summary'] = {
            'total_elements_analyzed': len(all_elements),
            'elements_after_filtering': len(filtered_elements),
            'elements_with_target_layers': len(set(d['element_id'] for d in target_layers_data)),
            'total_target_layers_found': len(target_layers_data),
            'unique_element_types': len(by_type),
            'element_types_found': list(by_type.keys())
        }
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'elements_analyzed': 0,
            'target_layers_found': 0,
            'summary': {},
            'by_type': {},
            'layer_details': []
        }