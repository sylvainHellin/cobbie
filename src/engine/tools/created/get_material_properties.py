
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def get_material_properties(
    ifc_file_path: str,
    material_name_or_entity: Union[str, ifcopenshell.entity_instance],
    property_names: List[str],
    property_set_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Retrieve specific property values directly from a material entity in an IFC model.
    
    This function searches for properties in material-specific property sets, which may contain 
    information not available through element-level property extraction.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        material_name_or_entity: Either a material name (str) or a material entity instance from IfcOpenShell
        property_names (List[str]): List of property names to look for (e.g., ['ExpectedLife', 'ThermalTransmittance', 'Density'])
        property_set_names (Optional[List[str]]): Optional list of property set names to search within 
                                                  (e.g., ['Pset_MaterialCommon', 'Pset_ConcreteMaterial'])
    
    Returns:
        Dict[str, Any]: Dictionary mapping property names to their values. If a property is not found, its value will be None.
    """
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Handle material_name_or_entity as string or entity
    if isinstance(material_name_or_entity, str):
        # Find the material entity by name
        material_entity = None
        materials = ifc_file.by_type("IfcMaterial")
        for material in materials:
            if hasattr(material, 'Name') and material.Name == material_name_or_entity:
                material_entity = material
                break
        if material_entity is None:
            raise ValueError(f"Material '{material_name_or_entity}' not found in the IFC model")
    else:
        # Assume it's already a material entity
        material_entity = material_name_or_entity
    
    # Initialize result dictionary with None values
    result = {prop_name: None for prop_name in property_names}
    
    # Try to get property sets directly associated with the material
    psets = {}
    try:
        psets = ifcopenshell.util.element.get_psets(material_entity)
    except Exception:
        # If we can't get psets directly from material, try to find them through elements
        material_relations = ifc_file.by_type("IfcRelAssociatesMaterial")
        for rel in material_relations:
            if hasattr(rel, 'RelatingMaterial') and rel.RelatingMaterial == material_entity:
                # Get psets from the elements that use this material
                for element in rel.RelatedObjects:
                    try:
                        element_psets = ifcopenshell.util.element.get_psets(element)
                        # Merge with existing psets
                        for pset_name, pset_dict in element_psets.items():
                            if pset_name not in psets:
                                psets[pset_name] = pset_dict
                            else:
                                psets[pset_name].update(pset_dict)
                    except Exception:
                        continue
    
    # If we still don't have psets, search through all property sets in the model
    if not psets:
        all_psets = ifc_file.by_type("IfcPropertySet")
        for pset in all_psets:
            # If specific property set names are provided, check if current pset is in that list
            if property_set_names and hasattr(pset, 'Name') and pset.Name not in property_set_names:
                continue
                
            if hasattr(pset, 'HasProperties'):
                pset_dict = {}
                for prop in pset.HasProperties:
                    if hasattr(prop, 'NominalValue'):
                        value = prop.NominalValue.wrappedValue if hasattr(prop.NominalValue, 'wrappedValue') else prop.NominalValue
                        pset_dict[prop.Name] = value
                if hasattr(pset, 'Name'):
                    psets[pset.Name] = pset_dict
    
    # Search for properties in the property sets
    prop_names_lower = [prop.lower() for prop in property_names]
    
    for pset_name, pset_dict in psets.items():
        # If specific property set names are provided, check if current pset is in that list
        if property_set_names and pset_name not in property_set_names:
            continue
            
        # Search for each property name in the current property set
        for prop_name, prop_value in pset_dict.items():
            prop_name_lower = prop_name.lower()
            # Check if this property name matches any of our requested properties (case-insensitive)
            for i, target_prop_lower in enumerate(prop_names_lower):
                if prop_name_lower == target_prop_lower and result[property_names[i]] is None:
                    result[property_names[i]] = prop_value
    
    return result
