import ifcopenshell
from typing import List, Dict, Any, Optional

def discover_coverings_comprehensive(
    ifc_file: ifcopenshell.file,
    target_element_types: List[str] = ['IfcSlab', 'IfcWall'],
    covering_keywords: List[str] = ['finish', 'covering', 'paint', 'tile', 'carpet', 'floor', 'wall', 'ceiling', 'coating'],
    include_dedicated_coverings: bool = True,
    include_proxy_elements: bool = True,
    categorize_by_element_type: bool = True,
    max_examples_per_category: int = 5
) -> Dict[str, Any]:
    """
    Discovers coverings in an IFC model using a comprehensive multi-strategy approach.
    
    This function implements a workflow of checking for dedicated IfcCovering elements first,
    then falling back to material analysis from specified building elements when dedicated
    coverings are not found. It handles the common BIM analysis pattern where domain-specific
    elements might be represented as dedicated elements or as materials on other building components.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        target_element_types: List of element types to analyze for covering materials
        covering_keywords: List of keywords to identify covering materials
        include_dedicated_coverings: Boolean to check for IfcCovering elements
        include_proxy_elements: Boolean to check IfcBuildingElementProxy for coverings
        categorize_by_element_type: Boolean to group results by element type
        max_examples_per_category: Maximum examples to show per category
    
    Returns:
        Dict containing:
        - 'dedicated_coverings': List of IfcCovering elements found
        - 'covering_materials': Dict of materials categorized by type (floor, wall, etc.)
        - 'proxy_coverings': List of BuildingElementProxy elements identified as coverings
        - 'summary': Dict with counts and statistics
        - 'discovery_strategy': String indicating which strategy was successful
    
    Example:
        >>> import ifcopenshell
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = discover_coverings_comprehensive(ifc_file)
        >>> print(result['discovery_strategy'])
        'material_analysis'
        >>> print(result['summary']['total_coverings_found'])
        15
    """
    
    result = {
        'dedicated_coverings': [],
        'covering_materials': {},
        'proxy_coverings': [],
        'summary': {},
        'discovery_strategy': 'none'
    }
    
    try:
        # Strategy 1: Check for dedicated IfcCovering elements
        if include_dedicated_coverings:
            dedicated_coverings = ifc_file.by_type('IfcCovering')
            result['dedicated_coverings'] = [
                {
                    'id': covering.id(),
                    'name': covering.Name,
                    'object_type': covering.ObjectType,
                    'predefined_type': covering.PredefinedType
                }
                for covering in dedicated_coverings
            ]
            
            if result['dedicated_coverings']:
                result['discovery_strategy'] = 'dedicated_coverings'
        
        # Strategy 2: Material analysis from target elements
        def get_element_materials(element):
            """Extract materials from an element using IfcRelAssociatesMaterial"""
            materials = []
            try:
                for rel in ifc_file.get_inverse(element):
                    if rel.is_a('IfcRelAssociatesMaterial'):
                        material_select = rel.RelatingMaterial
                        if material_select.is_a('IfcMaterial'):
                            materials.append(material_select)
                        elif material_select.is_a('IfcMaterialLayerSet'):
                            for layer in material_select.MaterialLayers:
                                if layer.Material:
                                    materials.append(layer.Material)
                        elif material_select.is_a('IfcMaterialConstituentSet'):
                            for constituent in material_select.MaterialConstituents:
                                if constituent.Material:
                                    materials.append(constituent.Material)
            except Exception:
                pass
            return materials
        
        # Analyze materials from target element types
        covering_materials_by_type = {}
        all_materials_found = set()
        
        for element_type in target_element_types:
            try:
                elements = ifc_file.by_type(element_type)
                if not elements:
                    continue
                    
                type_materials = set()
                type_examples = []
                
                for element in elements:
                    materials = get_element_materials(element)
                    for material in materials:
                        if material.Name:
                            material_name = material.Name
                            type_materials.add(material_name)
                            all_materials_found.add(material_name)
                            
                            # Check if material matches covering keywords
                            material_name_lower = material_name.lower()
                            is_covering = any(keyword in material_name_lower for keyword in covering_keywords)
                            
                            if is_covering and len(type_examples) < max_examples_per_category:
                                type_examples.append({
                                    'element_name': element.Name,
                                    'element_id': element.id(),
                                    'material_name': material_name,
                                    'material_id': material.id()
                                })
                
                if type_materials:
                    covering_materials_by_type[element_type] = {
                        'materials': list(type_materials),
                        'count': len(type_materials),
                        'examples': type_examples
                    }
                    
            except Exception:
                continue
        
        result['covering_materials'] = covering_materials_by_type
        
        # Strategy 3: Check IfcBuildingElementProxy for covering-related elements
        if include_proxy_elements:
            try:
                proxies = ifc_file.by_type('IfcBuildingElementProxy')
                covering_proxies = []
                
                for proxy in proxies:
                    if proxy.Name:
                        name_lower = proxy.Name.lower()
                        if any(keyword in name_lower for keyword in covering_keywords):
                            materials = get_element_materials(proxy)
                            covering_proxies.append({
                                'id': proxy.id(),
                                'name': proxy.Name,
                                'object_type': proxy.ObjectType,
                                'materials': [m.Name for m in materials if m.Name]
                            })
                
                result['proxy_coverings'] = covering_proxies
            except Exception:
                pass
        
        # Determine discovery strategy
        if not result['dedicated_coverings'] and covering_materials_by_type:
            result['discovery_strategy'] = 'material_analysis'
        elif not result['dedicated_coverings'] and not covering_materials_by_type and result['proxy_coverings']:
            result['discovery_strategy'] = 'proxy_elements'
        
        # Create summary
        result['summary'] = {
            'dedicated_coverings_count': len(result['dedicated_coverings']),
            'covering_materials_count': len(all_materials_found),
            'proxy_coverings_count': len(result['proxy_coverings']),
            'total_coverings_found': len(result['dedicated_coverings']) + len(all_materials_found) + len(result['proxy_coverings']),
            'element_types_analyzed': len(target_element_types),
            'strategies_used': [
                'dedicated_coverings' if include_dedicated_coverings else None,
                'material_analysis' if target_element_types else None,
                'proxy_elements' if include_proxy_elements else None
            ],
            'unique_materials': list(all_materials_found)
        }
        
    except Exception as e:
        result['error'] = str(e)
    
    return result