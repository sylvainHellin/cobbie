import ifcopenshell
from typing import List, Dict, Union, Optional
import ifcopenshell.util.element

def get_materials_for_elements(
    model: ifcopenshell.file, 
    element_types: List[str], 
    group_by_type: bool = False, 
    check_type_objects: bool = False
) -> Union[Dict[str, List[str]], List[str]]:
    """
    Retrieves unique material names associated with specific IFC element types.
    
    Handles direct assignment, layer sets, and layer set usages. This function 
    abstracts the complexity of material relationship traversal and aggregation.
    
    Args:
        model: The IFC model instance.
        element_types: List of IFC entity types to analyze (e.g., ['IfcBeam', 'IfcColumn']).
        group_by_type: If True, returns a dict mapping element types to lists of 
                       material names. If False, returns a flat list of unique 
                       material names.
        check_type_objects: If True, attempts to find material associations on the 
                           Type definitions if instances have none.
    
    Returns:
        Dict[str, List[str]] or List[str]: Material names associated with the 
        specified elements. Returns empty dict/list if no materials found.
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> materials = get_materials_for_elements(model, ['IfcBeam', 'IfcColumn'])
        >>> print(materials)
        ['Metal - Steel - 345 MPa']
        
        >>> materials_by_type = get_materials_for_elements(
        ...     model, ['IfcBeam', 'IfcColumn'], group_by_type=True
        ... )
        >>> print(materials_by_type)
        {'IfcBeam': ['Metal - Steel - 345 MPa'], 
         'IfcColumn': ['Metal - Steel - 345 MPa']}
    """
    if not element_types:
        return {} if group_by_type else []
    
    all_materials = set()
    materials_by_type = {}
    skipped_elements = 0
    
    for elem_type in element_types:
        try:
            elements = model.by_type(elem_type)
        except RuntimeError:
            # Entity type not found in schema
            if group_by_type:
                materials_by_type[elem_type] = []
            continue
            
        materials_for_type = set()
        
        for elem in elements:
            try:
                # Use utility function to get all materials (handles inheritance, sets, usages)
                materials = ifcopenshell.util.element.get_materials(elem, should_inherit=True)
                
                if materials:
                    for mat in materials:
                        mat_name = getattr(mat, 'Name', None)
                        if mat_name:
                            materials_for_type.add(mat_name)
                            all_materials.add(mat_name)
                elif check_type_objects:
                    # Try to get material from type definition if instance has none
                    try:
                        type_obj = ifcopenshell.util.element.get_type(elem)
                        if type_obj:
                            type_materials = ifcopenshell.util.element.get_materials(
                                type_obj, should_inherit=False
                            )
                            for mat in type_materials:
                                mat_name = getattr(mat, 'Name', None)
                                if mat_name:
                                    materials_for_type.add(mat_name)
                                    all_materials.add(mat_name)
                    except (AttributeError, RuntimeError):
                        pass
                        
            except (AttributeError, RuntimeError):
                skipped_elements += 1
                continue
        
        materials_by_type[elem_type] = sorted(materials_for_type)
    
    if skipped_elements > 0:
        print(f"Warning: Skipped {skipped_elements} elements due to errors")
    
    if group_by_type:
        return materials_by_type
    else:
        return sorted(all_materials)