import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def get_material_distribution_for_elements(
    model: ifcopenshell.file,
    ifc_type: str,
    filter_pset_name: Optional[str] = None,
    filter_prop_name: Optional[str] = None,
    filter_value: Optional[Any] = None,
    predefined_type: Optional[str] = None,
    group_by_layer: bool = False,
    include_percentages: bool = True,
    sort_by: str = 'count'
) -> Dict[str, Dict[str, Any]]:
    """
    Analyzes the material composition of a filtered subset of IFC elements and returns
    the distribution (count and percentage) of materials used.

    This function combines element filtering (by property values and PredefinedType) 
    with material relationship traversal to answer questions like 'What materials are 
    used for the exterior walls?' or 'How many elements of Type X are made of Material Y?'.

    Args:
        model: The loaded IFC model.
        ifc_type: The IFC class to analyze (e.g., 'IfcWallStandardCase', 'IfcCovering').
        filter_pset_name: Property set name to filter elements (e.g., 'ArchiCADProperties').
        filter_prop_name: Property name to filter elements (e.g., 'Ebene').
        filter_value: Value to match for filtering (e.g., 'Außenwände').
        predefined_type: Filter by IFC PredefinedType attribute (e.g., 'CEILING', 'FLOOR').
                         Comparison is case-insensitive. Elements without this attribute
                         will be excluded if this filter is active.
        group_by_layer: If True, groups by specific material layer names; if False,
                       groups by the primary material name (default False).
        include_percentages: Whether to include percentage calculations (default True).
        sort_by: Sort results by 'count', 'name', or 'none' (default 'count').

    Returns:
        A dictionary where keys are material names and values contain 'count' and
        optionally 'percentage'. Example:
        {
            'Concrete': {'count': 10, 'percentage': 50.0},
            'Brick': {'count': 10, 'percentage': 50.0}
        }
    """
    # Validate inputs
    if model is None:
        raise ValueError("Model cannot be None")
    
    if not ifc_type:
        raise ValueError("ifc_type must be specified")
    
    # Get all elements of the specified type
    elements = model.by_type(ifc_type)
    
    if not elements:
        return {}
    
    # Filter elements
    filtered_elements = []
    skipped_elements = 0
    
    for element in elements:
        try:
            # 1. Check PredefinedType Filter
            type_match = True
            if predefined_type is not None:
                # Check if element has the attribute
                if hasattr(element, 'PredefinedType'):
                    ptype_val = getattr(element, 'PredefinedType')
                    if ptype_val is not None:
                        # Case-insensitive comparison
                        type_match = str(ptype_val).strip().upper() == predefined_type.strip().upper()
                    else:
                        # Attribute exists but is null/None, so it doesn't match
                        type_match = False
                else:
                    # Attribute does not exist on this element type
                    type_match = False
            
            # 2. Check Property Set Filter
            pset_match = True
            if filter_pset_name and filter_prop_name and filter_value is not None:
                psets = ifcopenshell.util.element.get_psets(element)
                if psets and filter_pset_name in psets:
                    prop_value = psets[filter_pset_name].get(filter_prop_name)
                    pset_match = (prop_value == filter_value)
                else:
                    # Pset or property not found, does not match
                    pset_match = False
            
            # Combine filters (AND logic)
            if type_match and pset_match:
                filtered_elements.append(element)
                
        except (AttributeError, KeyError, RuntimeError) as e:
            skipped_elements += 1
            continue
    
    if not filtered_elements:
        return {}
    
    # Count materials
    material_counts: Dict[str, int] = {}
    missing_material_count = 0
    
    for element in filtered_elements:
        try:
            materials = ifcopenshell.util.element.get_materials(element)
            
            if not materials:
                missing_material_count += 1
                continue
            
            if group_by_layer:
                # Group by individual material layers
                for mat in materials:
                    if mat.is_a('IfcMaterialLayerSet'):
                        if hasattr(mat, 'MaterialLayers'):
                            for layer in mat.MaterialLayers:
                                layer_mat = getattr(layer, 'Material', None)
                                if layer_mat and hasattr(layer_mat, 'Name'):
                                    mat_name = layer_mat.Name or 'Unnamed'
                                    material_counts[mat_name] = material_counts.get(mat_name, 0) + 1
                    elif hasattr(mat, 'Name'):
                        mat_name = mat.Name or 'Unnamed'
                        material_counts[mat_name] = material_counts.get(mat_name, 0) + 1
            else:
                # Group by primary material name
                for mat in materials:
                    if hasattr(mat, 'Name'):
                        mat_name = mat.Name or 'Unnamed'
                        material_counts[mat_name] = material_counts.get(mat_name, 0) + 1
        except (AttributeError, KeyError, RuntimeError) as e:
            skipped_elements += 1
            continue
    
    # Build result dictionary with counts and percentages
    total_with_materials = sum(material_counts.values())
    
    result: Dict[str, Dict[str, Any]] = {}
    for mat_name, count in material_counts.items():
        result[mat_name] = {'count': count}
        if include_percentages and total_with_materials > 0:
            result[mat_name]['percentage'] = round((count / total_with_materials) * 100, 1)
    
    # Add missing material info if any
    if missing_material_count > 0:
        result['Unknown/No Material'] = {'count': missing_material_count}
        if include_percentages and total_with_materials > 0:
            result['Unknown/No Material']['percentage'] = round(
                (missing_material_count / (total_with_materials + missing_material_count)) * 100, 1
            )
    
    # Sort results
    if sort_by == 'count':
        result = dict(sorted(result.items(), key=lambda x: x[1]['count'], reverse=True))
    elif sort_by == 'name':
        result = dict(sorted(result.items(), key=lambda x: x[0].lower()))
    
    return result