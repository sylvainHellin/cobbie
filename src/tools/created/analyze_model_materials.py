import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any, List, Set

def analyze_model_materials(
    model: ifcopenshell.file,
    include_layer_sets: bool = True,
    include_type_objects: bool = True,
    include_properties: bool = True,
    sample_size: int = 10,
    return_details: bool = True
) -> Dict[str, Any]:
    """
    Performs comprehensive analysis of all materials defined in an IFC model.

    This function investigates multiple sources of material information (direct materials,
    layer sets, type objects, property sets) to determine what material data exists and
    how it is structured. It is particularly useful for assessing data completeness when
    standard material queries return generic or placeholder names.

    Args:
        model (ifcopenshell.file): The IFC model instance.
        include_layer_sets (bool): If True, analyzes material layer sets and thicknesses.
            Defaults to True.
        include_type_objects (bool): If True, checks Type Objects for material associations.
            Defaults to True.
        include_properties (bool): If True, checks for material properties. Defaults to True.
        sample_size (int): Number of items to sample when listing details (prevents massive output).
            Defaults to 10.
        return_details (bool): If True, returns detailed structure with all information.
            If False, returns summary counts only. Defaults to True.

    Returns:
        Dict[str, Any]: A comprehensive material analysis containing:
            - 'material_entities': Count of IfcMaterial entities
            - 'layer_sets': Count of IfcMaterialLayerSet entities
            - 'layer_set_usages': Count of IfcMaterialLayerSetUsage entities
            - 'unique_material_names': List of unique material names found
            - 'materials_with_properties': Count of materials that have property definitions
            - 'type_object_materials': Material associations found in Type Objects (if analyzed)
            - 'material_property_sets': Property sets containing material-related info (if analyzed)
            - 'sample_layer_sets': Sample of layer set details (if include_layer_sets)

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> analysis = analyze_model_materials(model, sample_size=5)
        >>> print(analysis['material_entities'])
        195
    """
    # Initialize result dictionary with default values
    result: Dict[str, Any] = {
        'material_entities': 0,
        'layer_sets': 0,
        'layer_set_usages': 0,
        'unique_material_names': [],
        'materials_with_properties': 0,
        'type_object_materials': [],
        'material_property_sets': [],
        'sample_layer_sets': []
    }

    if model is None:
        return result

    # --- 1. Basic Material Entities ---
    try:
        materials = model.by_type('IfcMaterial')
        result['material_entities'] = len(materials)
        
        unique_names: Set[str] = set()
        mats_with_props_count = 0
        
        for mat in materials:
            # Safely get material name
            name = getattr(mat, 'Name', None)
            if name is None:
                name = "Unnamed"
            unique_names.add(name)
            
            # Check properties if enabled
            if include_properties:
                try:
                    if hasattr(mat, 'HasProperties') and mat.HasProperties:
                        mats_with_props_count += 1
                except AttributeError:
                    pass
                    
        result['unique_material_names'] = sorted(list(unique_names))
        result['materials_with_properties'] = mats_with_props_count
        
    except RuntimeError:
        # Schema might not support IfcMaterial (unlikely but defensive)
        pass
    except Exception as e:
        print(f"Warning: Error accessing IfcMaterial: {e}")

    # --- 2. Layer Sets and Usages ---
    if include_layer_sets:
        # Get Layer Sets
        try:
            layer_sets = model.by_type('IfcMaterialLayerSet')
            result['layer_sets'] = len(layer_sets)
            
            # Sample details if requested
            if return_details and layer_sets:
                sample_sets = layer_sets[:sample_size]
                for ls in sample_sets:
                    layer_details = []
                    try:
                        # Access layers safely
                        if hasattr(ls, 'MaterialLayers') and ls.MaterialLayers:
                            for layer in ls.MaterialLayers:
                                mat_name = "Unnamed"
                                if hasattr(layer, 'Material') and layer.Material:
                                    mat_name = getattr(layer.Material, 'Name', "Unnamed")
                                
                                thickness = "N/A"
                                if hasattr(layer, 'LayerThickness'):
                                    thickness = layer.LayerThickness
                                    
                                layer_details.append({
                                    'material_name': mat_name,
                                    'thickness': thickness
                                })
                        result['sample_layer_sets'].append(layer_details)
                    except (AttributeError, TypeError):
                        result['sample_layer_sets'].append([{'error': 'Could not parse layer structure'}])
                        
        except RuntimeError:
            # IfcMaterialLayerSet not in schema
            pass
        except Exception as e:
            print(f"Warning: Error accessing IfcMaterialLayerSet: {e}")
            
        # Get Layer Set Usages
        try:
            usages = model.by_type('IfcMaterialLayerSetUsage')
            result['layer_set_usages'] = len(usages)
        except RuntimeError:
            pass
        except Exception as e:
            print(f"Warning: Error accessing IfcMaterialLayerSetUsage: {e}")

    # --- 3. Type Objects Analysis ---
    if include_type_objects:
        try:
            type_objects = model.by_type('IfcTypeObject')
            type_mats_info: List[Dict[str, Any]] = []
            
            if return_details and type_objects:
                # Sample type objects to prevent massive output
                sample_tos = type_objects[:sample_size]
                for to in sample_tos:
                    try:
                        # Check associations safely
                        if hasattr(to, 'HasAssociations') and to.HasAssociations:
                            for assoc in to.HasAssociations:
                                if assoc.is_a() == 'IfcRelAssociatesMaterial':
                                    rel_mat = getattr(assoc, 'RelatingMaterial', None)
                                    if rel_mat:
                                        mat_name = getattr(rel_mat, 'Name', 'Unnamed')
                                        type_mats_info.append({
                                            'type_object': getattr(to, 'Name', 'Unnamed'),
                                            'type_class': to.is_a(),
                                            'material_type': rel_mat.is_a(),
                                            'material_name': mat_name
                                        })
                    except AttributeError:
                        continue
            
            result['type_object_materials'] = type_mats_info
            
        except RuntimeError:
            pass
        except Exception as e:
            print(f"Warning: Error analyzing Type Objects: {e}")

    # --- 4. Property Sets Analysis ---
    if include_properties and return_details:
        found_property_sets: Set[str] = set()
        # Check a sample of building elements for material-related psets
        element_types_to_check = ['IfcWall', 'IfcSlab', 'IfcRoof', 'IfcColumn', 'IfcBeam', 'IfcWindow', 'IfcDoor']
        elements_checked = 0
        
        for etype in element_types_to_check:
            if elements_checked >= sample_size:
                break
                
            try:
                elements = model.by_type(etype)
                if not elements:
                    continue
                    
                # Check a sample of elements of this type
                for elem in elements[:sample_size]:
                    if elements_checked >= sample_size:
                        break
                    try:
                        psets = ifcopenshell.util.element.get_psets(elem)
                        for pset_name in psets.keys():
                            # Simple keyword check for material relevance
                            if pset_name and 'material' in pset_name.lower():
                                found_property_sets.add(pset_name)
                        elements_checked += 1
                    except (RuntimeError, AttributeError, TypeError):
                        continue
            except RuntimeError:
                # Entity type not in schema
                continue
                
        result['material_property_sets'] = sorted(list(found_property_sets))

    return result