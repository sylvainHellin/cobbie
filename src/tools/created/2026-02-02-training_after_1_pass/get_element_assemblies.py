import ifcopenshell
from typing import List, Dict, Any, Union


def get_element_assemblies(
    model: ifcopenshell.file,
    elements: List[ifcopenshell.entity_instance],
    include_properties: bool = True,
    include_constituents: bool = False
) -> Dict[ifcopenshell.entity_instance, List[Dict[str, Any]]]:
    """
    Extracts detailed construction assembly information (material layers and material constituents)
    from IFC elements. This function handles the navigation of material associations,
    specifically handling IfcMaterialLayerSetUsage, IfcMaterialLayerSet, and IfcMaterialConstituentSet.

    Args:
        model (ifcopenshell.file): The IFC model instance.
        elements (List[ifcopenshell.entity_instance]): A list of IFC elements (e.g., walls, slabs, roofs) to analyze.
        include_properties (bool): If True, attempts to fetch layer/constituent properties (e.g., IsVentilated). Defaults to True.
        include_constituents (bool): If True, checks for IfcMaterialConstituentSet if no LayerSet is found.
                                     Defaults to False to maintain backward compatibility.

    Returns:
        Dict[ifcopenshell.entity_instance, List[Dict[str, Any]]]: A dictionary mapping each input element to a list of its assembly components.
        
        If `include_constituents` is False (default):
            Returns list of dicts for layers only. Keys: 'material_name', 'thickness' (optional), etc.
            Elements without layer sets return an empty list.
        
        If `include_constituents` is True:
            Returns list of dicts with an additional 'assembly_type' key ('layer' or 'constituent').
            'layer' dicts contain: 'assembly_type', 'material_name', 'thickness', etc.
            'constituent' dicts contain: 'assembly_type', 'material_name', 'constituent_name', 'fraction'.
            Elements without assembly data return an empty list.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> walls = model.by_type('IfcWall')
        >>> # Old usage (backward compatible)
        >>> assemblies = get_element_assemblies(model, walls)
        >>> for wall, layers in assemblies.items():
        ...     print(f"{wall.Name}: {layers}")
        >>> roofs = model.by_type('IfcRoof')
        >>> # New usage (enhanced)
        >>> assemblies = get_element_assemblies(model, roofs, include_constituents=True)
        >>> for roof, comps in assemblies.items():
        ...     for c in comps:
        ...         if c['assembly_type'] == 'constituent':
        ...             print(f"Constituent: {c['material_name']}")
    """
    if not elements:
        return {}

    results: Dict[ifcopenshell.entity_instance, List[Dict[str, Any]]] = {}
    skipped_count = 0

    for element in elements:
        try:
            assembly_data: List[Dict[str, Any]] = []
            
            # --- Attempt 1: Check for Material Layer Set (Standard for Walls/Slabs) ---
            # Use ifcopenshell utility to get the material.
            # should_skip_usage=True gets the MaterialLayerSet directly instead of the Usage wrapper.
            # should_inherit=True ensures materials from Type definitions are retrieved if not on the instance.
            material = ifcopenshell.util.element.get_material(
                element, 
                should_skip_usage=True, 
                should_inherit=True
            )

            if material and material.is_a('IfcMaterialLayerSet'):
                if hasattr(material, 'MaterialLayers'):
                    for layer in material.MaterialLayers:
                        layer_info: Dict[str, Any] = {}
                        
                        # Extract Material Name
                        mat_name = 'Unknown'
                        if hasattr(layer, 'Material') and layer.Material:
                            mat_name = getattr(layer.Material, 'Name', 'Unknown')
                        layer_info['material_name'] = mat_name
                        
                        # Extract Thickness
                        layer_info['thickness'] = getattr(layer, 'LayerThickness', None)
                        
                        if include_properties:
                            # Extract IsVentilated (boolean)
                            if hasattr(layer, 'IsVentilated'):
                                layer_info['is_ventilated'] = bool(layer.IsVentilated)
                            
                            # Extract Category (often used for function description like 'STRUCTURAL', 'FINISH')
                            if hasattr(layer, 'Category'):
                                layer_info['category'] = getattr(layer, 'Category', None)
                        
                        # Add assembly_type only if using the enhanced functionality
                        if include_constituents:
                            layer_info['assembly_type'] = 'layer'
                        
                        assembly_data.append(layer_info)
            
            # --- Attempt 2: Check for Material Constituent Set (If no Layer Set found) ---
            elif include_constituents:
                # Manual traversal of IfcRelAssociatesMaterial is more robust for finding
                # IfcMaterialConstituentSet specifically, as get_material might prioritize other types.
                
                rels = []
                # HasAssociations is available in IFC4. In IFC2x3 it is an inverse attribute.
                if hasattr(element, 'HasAssociations'):
                    rels = element.HasAssociations
                
                # If not found on instance, check Type Object (inheritance)
                if not rels and element.IsTypedBy:
                    type_obj = element.IsTypedBy[0].RelatingType
                    if hasattr(type_obj, 'HasAssociations'):
                        rels = type_obj.HasAssociations
                
                for rel in rels:
                    if rel.is_a('IfcRelAssociatesMaterial'):
                        mat_select = rel.RelatingMaterial
                        
                        if mat_select.is_a('IfcMaterialConstituentSet'):
                            constituent_set = mat_select
                            
                            if hasattr(constituent_set, 'MaterialConstituents'):
                                for constituent in constituent_set.MaterialConstituents:
                                    const_info: Dict[str, Any] = {}
                                    
                                    # Material Name
                                    mat_name = 'Unknown'
                                    if hasattr(constituent, 'Material') and constituent.Material:
                                        mat_name = getattr(constituent.Material, 'Name', 'Unknown')
                                    const_info['material_name'] = mat_name
                                    
                                    # Constituent Name (Role)
                                    const_info['constituent_name'] = getattr(constituent, 'Name', None)
                                    
                                    # Fraction
                                    const_info['fraction'] = getattr(constituent, 'Fraction', None)
                                    
                                    if include_properties:
                                        # Check for optional Description
                                        if hasattr(constituent, 'Description'):
                                            const_info['description'] = constituent.Description
                                    
                                    const_info['assembly_type'] = 'constituent'
                                    assembly_data.append(const_info)
                                # Break after finding the first valid set for this element to avoid duplicates
                                break 

            results[element] = assembly_data

        except (AttributeError, RuntimeError) as e:
            # Handle specific errors gracefully (e.g., missing attributes on corrupted elements)
            skipped_count += 1
            results[element] = []

    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} elements due to errors.")

    return results