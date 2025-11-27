import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Set, Union, Optional, Any

def extract_element_materials_comprehensive(
    ifc_file: ifcopenshell.file,
    elements: Union[List[ifcopenshell.entity_instance], str],
    material_property_keywords: List[str] = ['material', 'finish', 'surface', 'coating'],
    include_property_details: bool = True,
    max_examples: int = 10,
    element_filter_keywords: Optional[List[str]] = None,
    element_filter_fields: List[str] = ['Name', 'ObjectType'],
    case_sensitive_filter: bool = False
) -> Dict[str, Any]:
    """
    Extracts comprehensive material information from IFC elements by checking multiple sources:
    direct material associations, material layer sets, and material-related properties.
    
    This function answers questions like 'what materials are used in interior walls?' or 
    'what materials are specified for floors?' by systematically exploring all possible 
    material data sources in the IFC model.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        elements: List of IFC elements to analyze (or element_type string to auto-fetch)
        material_property_keywords: List of keywords to identify material-related properties
        include_property_details: Whether to include property set details
        max_examples: Maximum number of detailed examples to show
        element_filter_keywords: Keywords to filter elements by name/properties (optional)
        element_filter_fields: Fields to search for filter keywords (default ['Name', 'ObjectType'])
        case_sensitive_filter: Case sensitivity for keyword filtering (default False)
    
    Returns:
        Dict containing:
        - materials: Set of all unique materials found
        - material_details: List of material associations with element names and types
        - property_materials: Materials found in property sets
        - summary: Count of elements with materials and total materials found
        - filtered_elements: Number of elements after filtering (if filtering applied)
        - original_elements: Number of elements before filtering (if filtering applied)
    
    Example:
        >>> import ifcopenshell
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> # Get interior walls by filtering for 'Int' in names
        >>> result = extract_element_materials_comprehensive(
        ...     ifc_file, 
        ...     'IfcWall',
        ...     element_filter_keywords=['Int'],
        ...     element_filter_fields=['Name']
        ... )
        >>> print(f"Found {len(result['materials'])} materials: {result['materials']}")
    """
    # Helper function to filter out non-material values
    def is_likely_material(value: str) -> bool:
        """Filter out numeric values, empty strings, and other non-material properties"""
        if not value or value.strip() == '':
            return False
        # Filter out numeric values (including decimals)
        try:
            float(value)
            return False
        except ValueError:
            pass
        # Filter out boolean values
        if value.lower() in ['true', 'false']:
            return False
        # Filter out single characters or very short strings
        if len(value.strip()) < 2:
            return False
        # Filter out values that look like measurements (contain only numbers and units)
        if all(c.isdigit() or c in '. ,;-' for c in value):
            return False
        return True
    
    # Helper function to check if element matches filter keywords
    def element_matches_filter(element: ifcopenshell.entity_instance) -> bool:
        """Check if element matches any of the filter keywords in specified fields"""
        if not element_filter_keywords:
            return True  # No filtering applied
        
        for field in element_filter_fields:
            if hasattr(element, field):
                field_value = getattr(element, field)
                if field_value is not None:
                    field_str = str(field_value)
                    for keyword in element_filter_keywords:
                        if case_sensitive_filter:
                            if keyword in field_str:
                                return True
                        else:
                            if keyword.lower() in field_str.lower():
                                return True
        return False
    
    # Handle elements parameter
    if isinstance(elements, str):
        # Auto-fetch elements by type
        all_elements = ifc_file.by_type(elements)
    else:
        all_elements = elements
    
    # Apply semantic filtering if keywords provided
    if element_filter_keywords:
        elements = [elem for elem in all_elements if element_matches_filter(elem)]
    else:
        elements = all_elements
    
    # Initialize result structures
    materials_found: Set[str] = set()
    material_details: List[Dict[str, str]] = []
    property_materials: Set[str] = set()
    elements_with_materials = 0
    
    # Process each element
    for element in elements:
        element_name = element.Name if hasattr(element, 'Name') else 'Unknown'
        element_type = element.is_a()
        has_materials = False
        
        # 1. Check direct material associations
        try:
            materials = ifcopenshell.util.element.get_materials(element)
            if materials:
                has_materials = True
                for material in materials:
                    material_name = material.Name if hasattr(material, 'Name') else 'Unknown Material'
                    if is_likely_material(material_name):
                        materials_found.add(material_name)
                        material_details.append({
                            'element_name': element_name,
                            'element_type': element_type,
                            'material': material_name,
                            'source': 'direct_material'
                        })
        except Exception:
            pass  # Continue if material extraction fails
        
        # 2. Check material layer sets through HasAssociations
        try:
            for rel in element.HasAssociations:
                if hasattr(rel, 'RelatingMaterial'):
                    material = rel.RelatingMaterial
                    if material.is_a('IfcMaterialLayerSetUsage'):
                        layer_set = material.ForLayerSet
                        if layer_set and hasattr(layer_set, 'MaterialLayers'):
                            has_materials = True
                            for layer in layer_set.MaterialLayers:
                                if hasattr(layer, 'Material') and layer.Material:
                                    layer_material_name = layer.Material.Name if hasattr(layer.Material, 'Name') else 'Unknown Layer Material'
                                    if is_likely_material(layer_material_name):
                                        materials_found.add(layer_material_name)
                                        material_details.append({
                                            'element_name': element_name,
                                            'element_type': element_type,
                                            'material': layer_material_name,
                                            'source': 'material_layer'
                                        })
                    elif material.is_a('IfcMaterialLayerSet'):
                        if hasattr(material, 'MaterialLayers'):
                            has_materials = True
                            for layer in material.MaterialLayers:
                                if hasattr(layer, 'Material') and layer.Material:
                                    layer_material_name = layer.Material.Name if hasattr(layer.Material, 'Name') else 'Unknown Layer Material'
                                    if is_likely_material(layer_material_name):
                                        materials_found.add(layer_material_name)
                                        material_details.append({
                                            'element_name': element_name,
                                            'element_type': element_type,
                                            'material': layer_material_name,
                                            'source': 'material_layer'
                                        })
        except Exception:
            pass  # Continue if layer extraction fails
        
        # 3. Check property sets for material-related information
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            for pset_name, pset_data in psets.items():
                if isinstance(pset_data, dict):
                    for prop_name, prop_value in pset_data.items():
                        # Check if property name contains material keywords
                        if any(keyword.lower() in prop_name.lower() for keyword in material_property_keywords):
                            if prop_value is not None:
                                prop_str = str(prop_value)
                                # Handle multiple values separated by semicolons
                                values = [v.strip() for v in prop_str.split(';') if v.strip()]
                                for value in values:
                                    if is_likely_material(value):
                                        property_materials.add(value)
                                        materials_found.add(value)
                                        if include_property_details:
                                            material_details.append({
                                                'element_name': element_name,
                                                'element_type': element_type,
                                                'material': value,
                                                'source': f'property_{pset_name}_{prop_name}'
                                            })
        except Exception:
            pass  # Continue if property extraction fails
        
        if has_materials:
            elements_with_materials += 1
    
    # Limit material details examples
    if len(material_details) > max_examples:
        material_details = material_details[:max_examples]
    
    # Prepare summary
    summary = {
        'total_elements': len(elements),
        'elements_with_materials': elements_with_materials,
        'total_unique_materials': len(materials_found),
        'direct_materials': len([d for d in material_details if d['source'] == 'direct_material']),
        'layer_materials': len([d for d in material_details if d['source'] == 'material_layer']),
        'property_materials': len(property_materials)
    }
    
    # Add filtering info if applied
    result = {
        'materials': materials_found,
        'material_details': material_details,
        'property_materials': property_materials,
        'summary': summary
    }
    
    if element_filter_keywords:
        result['filtered_elements'] = len(elements)
        result['original_elements'] = len(all_elements)
    
    return result