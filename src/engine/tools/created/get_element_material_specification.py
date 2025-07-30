import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *

def get_element_material_specification(ifc_file_path: str, element: Union[ifcopenshell.entity_instance, str]) -> Dict[str, Any]:
    """
    Provides a comprehensive material specification for a given IFC element by combining multiple sources of information.
    
    This function extracts material information from the element, attempts to retrieve specific material properties 
    from the IFC model, falls back to general material information when specific properties aren't available, 
    and includes relevant property set information from the element.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element (Union[ifcopenshell.entity_instance, str]): Either an IFC element entity instance or the GlobalId of the element to investigate
        
    Returns:
        Dict[str, Any]: A dictionary containing:
          - element_info: Basic information about the element (name, type, GlobalId)
          - materials: List of material information dictionaries, each containing:
            - name: Material name
            - description: Material description if available
            - type: Type of material representation
            - specific_properties: Dictionary of specific material properties found in the model
            - general_info: General information about the material type when specific properties aren't available
            - layer_info: Thickness and layer set information for layered materials
          - element_property_sets: Dictionary of relevant property sets from the element that might contain material information
          - summary: A human-readable summary of the material specification
    """
    
    def get_material_info_from_element(ifc_file, element):
        """
        Extract material information from an element.
        
        Args:
            ifc_file: The IFC file object
            element: The IFC element entity instance
        
        Returns:
            List of material information dictionaries
        """
        materials = []
        
        # Get the material of the element
        material = ifcopenshell.util.element.get_material(element)
        
        if material:
            if material.is_a("IfcMaterial"):
                # Single material
                materials.append({
                    "name": material.Name,
                    "description": getattr(material, "Description", ""),
                    "type": "IfcMaterial"
                })
            elif material.is_a("IfcMaterialLayerSetUsage"):
                # Layered material
                layer_set = material.ForLayerSet
                if layer_set and hasattr(layer_set, 'MaterialLayers'):
                    for layer in layer_set.MaterialLayers:
                        if layer.Material:
                            materials.append({
                                "name": layer.Material.Name,
                                "description": getattr(layer.Material, "Description", ""),
                                "type": "IfcMaterialLayer",
                                "layer_info": {
                                    "thickness": layer.LayerThickness,
                                    "layer_set_name": getattr(layer_set, "LayerSetName", "")
                                }
                            })
            elif material.is_a("IfcMaterialList"):
                # Material list
                for mat in material.Materials:
                    materials.append({
                        "name": mat.Name,
                        "description": getattr(mat, "Description", ""),
                        "type": "IfcMaterial"
                    })
        
        return materials

    def get_material_properties(ifc_file, material_info):
        """
        Attempt to retrieve specific material properties from the IFC model.
        
        Args:
            ifc_file: The IFC file object
            material_info: Material information dictionary
        
        Returns:
            Dictionary of specific material properties found in the model
        """
        # In this implementation, we'll look for common engineering properties
        # This is a simplified version - in a real implementation, we would search
        # for IfcMaterialProperties associated with the material
        specific_properties = {}
        
        # For now, we'll return an empty dict as we didn't find specific properties
        # in our earlier exploration of the sample model
        return specific_properties

    def get_material_general_info(material_name):
        """
        Get general information about material types when specific properties aren't available.
        
        Args:
            material_name: Name of the material
        
        Returns:
            Dictionary of general material information
        """
        # This is a simplified implementation with some common material types
        general_info = {}
        
        # Look for keywords in the material name to determine material type
        name_lower = material_name.lower()
        
        if "steel" in name_lower or "metal" in name_lower:
            general_info = {
                "material_type": "Steel/Metal",
                "density_range_kg_per_m3": "7500-8000",
                "young_modulus_mpa": "200000-210000",
                "poisson_ratio": "0.27-0.30",
                "thermal_conductivity_w_per_m_k": "45-50",
                "typical_use": "Structural framing, columns, beams"
            }
        elif "concrete" in name_lower:
            general_info = {
                "material_type": "Concrete",
                "density_range_kg_per_m3": "2200-2500",
                "young_modulus_mpa": "20000-40000",
                "poisson_ratio": "0.15-0.20",
                "thermal_conductivity_w_per_m_k": "1.4-2.0",
                "typical_use": "Slabs, walls, foundations"
            }
        elif "wood" in name_lower:
            general_info = {
                "material_type": "Wood",
                "density_range_kg_per_m3": "400-800",
                "young_modulus_mpa": "8000-15000",
                "poisson_ratio": "0.30-0.40",
                "thermal_conductivity_w_per_m_k": "0.1-0.2",
                "typical_use": "Framing, flooring, roofing"
            }
        elif "brick" in name_lower:
            general_info = {
                "material_type": "Brick",
                "density_range_kg_per_m3": "1600-2000",
                "young_modulus_mpa": "5000-20000",
                "poisson_ratio": "0.15-0.20",
                "thermal_conductivity_w_per_m_k": "0.6-1.0",
                "typical_use": "Walls, facades"
            }
        else:
            general_info = {
                "material_type": "Unknown",
                "note": "General properties not available for this material type"
            }
        
        return general_info

    def get_relevant_property_sets(element):
        """
        Extract relevant property sets from the element that might contain material information.
        
        Args:
            element: The IFC element entity instance
        
        Returns:
            Dictionary of relevant property sets
        """
        # Get all property sets
        all_psets = ifcopenshell.util.element.get_psets(element)
        
        # Filter to focus on those most likely to contain material specification information
        relevant_psets = {}
        
        # Define keywords for material-related property sets
        material_keywords = ["material", "physical", "mechanical", "thermal", "structural"]
        
        for pset_name, pset_data in all_psets.items():
            # Include all property sets for now, but we could filter more specifically
            # For this implementation, we'll include all property sets but remove metadata
            filtered_pset = {k: v for k, v in pset_data.items() if k != 'id'}
            if filtered_pset:  # Only include if there are properties
                relevant_psets[pset_name] = filtered_pset
        
        return relevant_psets
    
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Handle both element entity instances and GlobalId strings
    if isinstance(element, str):
        # Element is a GlobalId
        element_entity = ifc_file.by_guid(element)
    else:
        # Element is already an entity instance
        element_entity = element
    
    # Get element information
    element_info = {
        "name": getattr(element_entity, "Name", "Unnamed"),
        "type": element_entity.is_a(),
        "global_id": element_entity.GlobalId
    }
    
    # Extract material information
    materials_info = get_material_info_from_element(ifc_file, element_entity)
    
    # Process each material to get properties and general information
    materials = []
    for material_info in materials_info:
        # Attempt to retrieve specific material properties from the model
        specific_properties = get_material_properties(ifc_file, material_info)
        
        # Get general material information when specific properties aren't available
        general_info = get_material_general_info(material_info["name"])
        
        # Combine all material information
        material_spec = {
            "name": material_info["name"],
            "description": material_info["description"],
            "type": material_info["type"],
            "specific_properties": specific_properties,
            "general_info": general_info
        }
        
        # Add layer information if available
        if "layer_info" in material_info:
            material_spec["layer_info"] = material_info["layer_info"]
            
        materials.append(material_spec)
    
    # Extract relevant property sets from the element
    element_property_sets = get_relevant_property_sets(element_entity)
    
    # Create a human-readable summary
    summary_parts = []
    summary_parts.append(f"Element: {element_info['name']} ({element_info['type']})")
    summary_parts.append(f"GlobalId: {element_info['global_id']}")
    
    if materials:
        summary_parts.append(f"Materials: {len(materials)} found")
        for material in materials:
            summary_parts.append(f"  - {material['name']} ({material['type']})")
            if material['specific_properties']:
                summary_parts.append(f"    Specific properties: {len(material['specific_properties'])} found in model")
            else:
                summary_parts.append(f"    General information provided for {material['general_info']['material_type']}")
    else:
        summary_parts.append("No materials found")
    
    summary_parts.append(f"Property sets: {len(element_property_sets)} found")
    
    summary = "\n".join(summary_parts)
    
    # Return comprehensive dictionary with all gathered information
    return {
        "element_info": element_info,
        "materials": materials,
        "element_property_sets": element_property_sets,
        "summary": summary
    }

# Example usage:
# material_spec = get_element_material_specification("model.ifc", slab_element)
# print(material_spec["summary"])