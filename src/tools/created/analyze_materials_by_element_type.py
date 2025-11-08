import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Set, Any, Optional, Union

def analyze_materials_by_element_type(
    ifc_file: ifcopenshell.file,
    element_type: str,
    include_examples: bool = True,
    max_examples: int = 3
) -> Dict[str, Any]:
    """
    Analyzes materials used by different types of IFC elements, grouping results by element type.
    
    This function extracts material information from multiple sources including direct material
    associations (IfcMaterial) and material layer sets (IfcMaterialLayerSet), providing comprehensive
    material analysis with counts and examples for each element type.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcWall', 'IfcDoor', 'IfcSlab')
        include_examples: Boolean to include example element names for each type (default: True)
        max_examples: Maximum number of examples to store per type (default: 3)
    
    Returns:
        Dict containing:
            - total_elements: Total number of elements analyzed
            - element_types: Dict mapping element type names to:
                - count: Number of elements of this type
                - materials: Set of material names used
                - material_layers: List of material layer details (if applicable)
                - examples: List of example element names
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = analyze_materials_by_element_type(model, 'IfcWall')
        >>> print(f"Total walls: {result['total_elements']}")
        >>> for wall_type, info in result['element_types'].items():
        ...     print(f"{wall_type}: {info['materials']}")
    """
    try:
        # Initialize result structure
        result = {
            'total_elements': 0,
            'element_types': {}
        }
        
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        result['total_elements'] = len(elements)
        
        if not elements:
            return result
        
        # Process each element
        for element in elements:
            try:
                # Get element type/name
                element_type_obj = ifcopenshell.util.element.get_type(element)
                type_name = 'Unknown'
                
                if element_type_obj:
                    if hasattr(element_type_obj, 'Name') and element_type_obj.Name:
                        type_name = element_type_obj.Name
                    elif hasattr(element_type_obj, 'id'):
                        type_name = f"Type_{element_type_obj.id()}"
                
                # Initialize type entry if not exists
                if type_name not in result['element_types']:
                    result['element_types'][type_name] = {
                        'count': 0,
                        'materials': set(),
                        'material_layers': [],
                        'examples': []
                    }
                
                type_info = result['element_types'][type_name]
                type_info['count'] += 1
                
                # Check for material associations
                if hasattr(element, 'HasAssociations') and element.HasAssociations:
                    for rel in element.HasAssociations:
                        if rel.is_a('IfcRelAssociatesMaterial'):
                            material = rel.RelatingMaterial
                            
                            # Handle direct material
                            if material.is_a('IfcMaterial'):
                                if hasattr(material, 'Name') and material.Name:
                                    type_info['materials'].add(material.Name)
                            
                            # Handle material layer set
                            elif material.is_a('IfcMaterialLayerSet'):
                                if hasattr(material, 'MaterialLayers') and material.MaterialLayers:
                                    for layer in material.MaterialLayers:
                                        layer_info = {
                                            'layer_name': 'Unknown',
                                            'thickness': None
                                        }
                                        
                                        # Get layer material name
                                        if hasattr(layer, 'Material') and layer.Material:
                                            if hasattr(layer.Material, 'Name') and layer.Material.Name:
                                                layer_info['layer_name'] = layer.Material.Name
                                                type_info['materials'].add(layer.Material.Name)
                                        
                                        # Get layer thickness
                                        if hasattr(layer, 'LayerThickness'):
                                            layer_info['thickness'] = layer.LayerThickness
                                        
                                        type_info['material_layers'].append(layer_info)
                            
                            # Handle material profile set
                            elif material.is_a('IfcMaterialProfileSet'):
                                if hasattr(material, 'MaterialProfiles') and material.MaterialProfiles:
                                    for profile in material.MaterialProfiles:
                                        if hasattr(profile, 'Material') and profile.Material:
                                            if hasattr(profile.Material, 'Name') and profile.Material.Name:
                                                type_info['materials'].add(profile.Material.Name)
                            
                            # Handle material constituent set
                            elif material.is_a('IfcMaterialConstituentSet'):
                                if hasattr(material, 'MaterialConstituents') and material.MaterialConstituents:
                                    for constituent in material.MaterialConstituents:
                                        if hasattr(constituent, 'Material') and constituent.Material:
                                            if hasattr(constituent.Material, 'Name') and constituent.Material.Name:
                                                type_info['materials'].add(constituent.Material.Name)
                
                # Add examples if requested
                if include_examples and len(type_info['examples']) < max_examples:
                    element_name = 'Unnamed'
                    if hasattr(element, 'Name') and element.Name:
                        element_name = element.Name
                    elif hasattr(element, 'id'):
                        element_name = f"Element_{element.id()}"
                    type_info['examples'].append(element_name)
                    
            except Exception as e:
                # Continue processing other elements if one fails
                continue
        
        # Convert sets to lists for JSON serialization
        for type_name, type_info in result['element_types'].items():
            type_info['materials'] = list(type_info['materials'])
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'total_elements': 0,
            'element_types': {},
            'error': f"Error analyzing materials: {str(e)}"
        }