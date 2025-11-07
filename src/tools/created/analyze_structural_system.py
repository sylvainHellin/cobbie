import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_structural_system(
    ifc_file,
    structural_element_types: Optional[List[str]] = None,
    include_materials: bool = True,
    include_quantities: bool = True
) -> Dict[str, Any]:
    """
    Provides comprehensive analysis of a building's structural system by identifying structural elements,
    their materials, properties, and quantities.
    
    This function analyzes columns, beams, slabs, walls, and other structural elements to determine
    the structural system type, component breakdown, and material usage. It extracts key structural
    properties like LoadBearing status, dimensions, material associations, and categorizes elements
    by their properties.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        structural_element_types: Optional list of IFC types to analyze. 
            Defaults to common structural types: ['IfcColumn', 'IfcBeam', 'IfcSlab', 'IfcWall', 
            'IfcFooting', 'IfcFoundation', 'IfcStructuralMember']
        include_materials: Boolean to include material analysis (default: True)
        include_quantities: Boolean to include quantity analysis (default: True)
    
    Returns:
        Dict containing:
        - structural_system_type: Inferred structural system type
        - element_breakdown: Counts and categorization of structural elements
        - material_analysis: Material distribution and associations
        - structural_properties: Key structural properties like LoadBearing status
        - quantities: Element quantities if requested
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> analysis = analyze_structural_system(model)
        >>> print(f"Found {analysis['element_breakdown']['total_elements']} structural elements")
    """
    
    try:
        # Default structural element types if not provided
        if structural_element_types is None:
            structural_element_types = [
                'IfcColumn', 'IfcBeam', 'IfcSlab', 'IfcWall', 
                'IfcFooting', 'IfcFoundation', 'IfcStructuralMember'
            ]
        
        # Initialize result with all required keys
        result = {
            'structural_system_type': 'Unknown',
            'element_breakdown': {
                'total_elements': 0
            },
            'material_analysis': {
                'material_distribution': {},
                'total_materials': 0
            },
            'structural_properties': {
                'load_bearing_elements_by_type': {},
                'total_load_bearing_types': 0
            },
            'quantities': {}
        }
        
        # Count and analyze each structural element type
        total_structural_elements = 0
        material_counts = {}
        load_bearing_counts = {}
        
        for elem_type in structural_element_types:
            try:
                elements = ifc_file.by_type(elem_type)
                if not elements:
                    continue
                    
                element_count = len(elements)
                total_structural_elements += element_count
                
                # Basic element info
                result['element_breakdown'][elem_type] = {
                    'count': element_count,
                    'categories': {},
                    'properties_found': [],
                    'load_bearing_sample': 0
                }
                
                # Analyze sample elements for properties and materials
                sample_size = min(10, element_count)  # Sample up to 10 elements
                sampled_elements = elements[:sample_size]
                
                # Track categories and properties
                categories = {}
                properties_found = set()
                load_bearing_elements = 0
                
                for element in sampled_elements:
                    try:
                        # Get element type/name for categorization
                        element_name = getattr(element, 'Name', None) or 'Unnamed'
                        object_type = getattr(element, 'ObjectType', None)
                        category_key = f"{element_name}:{object_type}" if object_type else element_name
                        
                        categories[category_key] = categories.get(category_key, 0) + 1
                        
                        # Get properties using get_psets
                        try:
                            psets = ifcopenshell.util.element.get_psets(element)
                            for pset_name, pset_data in psets.items():
                                if isinstance(pset_data, dict):
                                    for prop_name, prop_value in pset_data.items():
                                        properties_found.add(f"{pset_name}.{prop_name}")
                                        
                                        # Track LoadBearing property specifically
                                        if prop_name.lower() == 'loadbearing' and prop_value is True:
                                            load_bearing_elements += 1
                        except Exception:
                            pass  # Skip if properties can't be retrieved
                        
                        # Get materials if requested
                        if include_materials:
                            try:
                                # Check material associations - use safer attribute access
                                if hasattr(element, 'HasAssociations') and element.HasAssociations:
                                    for assoc in element.HasAssociations:
                                        if hasattr(assoc, 'RelatingMaterial'):
                                            material = assoc.RelatingMaterial
                                            if hasattr(material, 'Name') and material.Name:
                                                material_name = material.Name
                                                material_counts[material_name] = material_counts.get(material_name, 0) + 1
                            except Exception:
                                pass  # Skip if materials can't be retrieved
                    except Exception:
                        continue  # Skip problematic elements
                
                # Store analysis results for this element type
                result['element_breakdown'][elem_type]['categories'] = categories
                result['element_breakdown'][elem_type]['properties_found'] = list(properties_found)
                result['element_breakdown'][elem_type]['load_bearing_sample'] = load_bearing_elements
                
                # Track load bearing by element type
                if load_bearing_elements > 0:
                    load_bearing_counts[elem_type] = load_bearing_elements
            except Exception:
                continue  # Skip problematic element types
        
        # Update total counts
        result['element_breakdown']['total_elements'] = total_structural_elements
        
        # Material analysis
        if include_materials:
            result['material_analysis'] = {
                'material_distribution': material_counts,
                'total_materials': len(material_counts)
            }
        
        # Structural properties summary
        result['structural_properties'] = {
            'load_bearing_elements_by_type': load_bearing_counts,
            'total_load_bearing_types': len(load_bearing_counts)
        }
        
        # Infer structural system type based on element distribution
        if total_structural_elements > 0:
            if 'IfcColumn' in result['element_breakdown'] and 'IfcBeam' in result['element_breakdown']:
                if result['element_breakdown']['IfcColumn']['count'] > 0 and result['element_breakdown']['IfcBeam']['count'] > 0:
                    result['structural_system_type'] = 'Frame Structure'
            elif 'IfcWall' in result['element_breakdown'] and result['element_breakdown']['IfcWall']['count'] > 0:
                result['structural_system_type'] = 'Load-bearing Wall Structure'
            elif 'IfcSlab' in result['element_breakdown'] and result['element_breakdown']['IfcSlab']['count'] > 0:
                result['structural_system_type'] = 'Slab Structure'
            
            # Add material-based inference if concrete is dominant
            if include_materials and material_counts:
                concrete_materials = [mat for mat in material_counts.keys() 
                                    if any(keyword in mat.lower() for keyword in ['beton', 'concrete', 'stb'])]
                if concrete_materials:
                    total_concrete = sum(material_counts[mat] for mat in concrete_materials)
                    if total_concrete > total_structural_elements * 0.5:  # More than 50% concrete
                        if result['structural_system_type'] == 'Frame Structure':
                            result['structural_system_type'] = 'Reinforced Concrete Frame Structure'
                        else:
                            result['structural_system_type'] = 'Reinforced Concrete Structure'
        else:
            result['structural_system_type'] = 'No Structural Elements Found'
        
        return result
        
    except Exception as e:
        # Return error result with all required keys
        return {
            'error': f'Failed to analyze structural system: {str(e)}',
            'structural_system_type': 'Error',
            'element_breakdown': {
                'total_elements': 0
            },
            'material_analysis': {
                'material_distribution': {},
                'total_materials': 0
            },
            'structural_properties': {
                'load_bearing_elements_by_type': {},
                'total_load_bearing_types': 0
            },
            'quantities': {}
        }