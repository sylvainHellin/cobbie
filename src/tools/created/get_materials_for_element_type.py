import ifcopenshell
from typing import Dict, List, Optional, Union

def get_materials_for_element_type(
    ifc_file: ifcopenshell.file,
    element_type: str,
    material_property_keywords: List[str] = ['material', 'finish', 'surface', 'coating'],
    include_property_sources: bool = True,
    case_sensitive: bool = False,
    sort_by_count: bool = True
) -> Dict:
    """
    Extracts and summarizes materials used for a specific IFC element type.
    
    This function provides a clean, focused answer to questions like 'what materials are used for walls?'
    by checking direct material associations, material layer sets, and material-related properties,
    then aggregating results with usage counts.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcSlab', 'IfcDoor')
        material_property_keywords: List of keywords to identify material-related properties
        include_property_sources: Whether to check material-related properties
        case_sensitive: Whether property keyword matching is case sensitive
        sort_by_count: Whether to sort results by usage count
    
    Returns:
        Dict with:
        - 'total_elements': Total number of elements analyzed
        - 'elements_with_materials': Number of elements with material data
        - 'materials': Dict mapping material names to {'count': int, 'source': str}
        - 'summary': String summary of findings
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = get_materials_for_element_type(ifc_file, 'IfcWall')
        >>> print(result['summary'])
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_elements = len(elements)
        
        if total_elements == 0:
            return {
                'total_elements': 0,
                'elements_with_materials': 0,
                'materials': {},
                'summary': f'No elements of type {element_type} found in the model.'
            }
        
        # Collect materials
        materials = {}
        elements_with_materials = 0
        
        # Prepare keywords for matching
        if not case_sensitive:
            keywords = [kw.lower() for kw in material_property_keywords]
        else:
            keywords = material_property_keywords
        
        for element in elements:
            element_has_materials = False
            
            # Check direct material associations
            if element.HasAssociations:
                for assoc in element.HasAssociations:
                    if assoc.is_a('IfcRelAssociatesMaterial'):
                        material = assoc.RelatingMaterial
                        if material:
                            element_has_materials = True
                            
                            if material.is_a('IfcMaterial'):
                                material_name = material.Name or 'Unnamed Material'
                                if material_name not in materials:
                                    materials[material_name] = {'count': 0, 'source': 'Direct'}
                                materials[material_name]['count'] += 1
                                
                            elif material.is_a('IfcMaterialLayerSet'):
                                for layer in material.MaterialLayers:
                                    if layer.Material:
                                        material_name = layer.Material.Name or 'Unnamed Layer Material'
                                        if material_name not in materials:
                                            materials[material_name] = {'count': 0, 'source': 'Layer'}
                                        materials[material_name]['count'] += 1
                            
                            elif material.is_a('IfcMaterialConstituentSet'):
                                for constituent in material.MaterialConstituents:
                                    if constituent.Material:
                                        material_name = constituent.Material.Name or 'Unnamed Constituent Material'
                                        if material_name not in materials:
                                            materials[material_name] = {'count': 0, 'source': 'Constituent'}
                                        materials[material_name]['count'] += 1
            
            # Check material-related properties
            if include_property_sources and element.IsDefinedBy:
                for definition in element.IsDefinedBy:
                    if definition.is_a('IfcRelDefinesByProperties'):
                        property_set = definition.RelatingPropertyDefinition
                        if property_set and property_set.is_a('IfcPropertySet'):
                            for prop in property_set.HasProperties:
                                if prop.is_a('IfcPropertySingleValue'):
                                    prop_name = prop.Name or ''
                                    if not case_sensitive:
                                        prop_name = prop_name.lower()
                                    
                                    # Check if property name contains any material keywords
                                    if any(keyword in prop_name for keyword in keywords):
                                        if prop.NominalValue:
                                            material_name = str(prop.NominalValue.wrappedValue)
                                            if material_name and material_name.strip():
                                                element_has_materials = True
                                                if material_name not in materials:
                                                    materials[material_name] = {'count': 0, 'source': 'Property'}
                                                materials[material_name]['count'] += 1
            
            if element_has_materials:
                elements_with_materials += 1
        
        # Sort materials by count if requested
        if sort_by_count:
            sorted_materials = dict(sorted(materials.items(), key=lambda x: x[1]['count'], reverse=True))
        else:
            sorted_materials = materials
        
        # Create summary
        total_unique_materials = len(sorted_materials)
        if total_unique_materials > 0:
            summary = f'Found {total_unique_materials} unique materials used for {elements_with_materials} out of {total_elements} {element_type} elements.'
        else:
            summary = f'No materials found for {total_elements} {element_type} elements.'
        
        return {
            'total_elements': total_elements,
            'elements_with_materials': elements_with_materials,
            'materials': sorted_materials,
            'summary': summary
        }
        
    except Exception as e:
        return {
            'total_elements': 0,
            'elements_with_materials': 0,
            'materials': {},
            'summary': f'Error analyzing materials: {str(e)}'
        }