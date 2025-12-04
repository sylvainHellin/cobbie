# python packages
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def get_element_material_layers_and_thicknesses(model: str = None, element_guid: str = None) -> str:
    """Gets detailed information about material layers and their thicknesses for a building element.
    
    This method retrieves the complete material composition of an IFC element, including:
    - Layer ordering from exterior to interior
    - Material names for each layer
    - Layer thicknesses in meters
    - Total element thickness
    
    Particularly useful for analyzing:
    - Wall assemblies
    - Floor/ceiling assemblies
    - Roof assemblies
    - Any other layered building elements
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        element_guid (str): The Global ID of the IFC element to analyze
            Example: "2O2Fr$t4X7Zf8NOew3FNhv"
            
    Returns:
        str: JSON string containing:
            {
                "element_type": The IFC class of the element,
                "element_name": Name of the element if available,
                "total_thickness": Sum of all layer thicknesses in meters,
                "layers": [
                    {
                        "index": Layer position (0 = exterior),
                        "material": Name of the material,
                        "thickness": Layer thickness in meters
                    },
                    ...
                ]
            }
            Returns error message if element not found or has no material layers
    """
    if not element_guid:
        return json.dumps({"error": "No element GUID provided"}, indent=2)
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    try:
        # Get the element by GUID
        element = ifc_model.by_guid(element_guid)
        if not element:
            return json.dumps({
                "error": f"No element found with GUID {element_guid}"
            }, indent=2)
            
        # Get material associations
        material_set = ifcopenshell.util.element.get_material(element)
        if not material_set:
            return json.dumps({
                "error": f"No material information found for element {element_guid}"
            }, indent=2)
            
        result = {
            "element_type": element.is_a(),
            "element_name": element.Name if element.Name else "Unnamed",
            "total_thickness": 0,
            "layers": []
        }
        
        # Handle material layer set usage
        if material_set.is_a('IfcMaterialLayerSetUsage'):
            layer_set = material_set.ForLayerSet
            for i, layer in enumerate(layer_set.MaterialLayers):
                layer_info = {
                    "index": i,
                    "material": layer.Material.Name if layer.Material else "Unknown",
                    "thickness": round(float(layer.LayerThickness), 3) if hasattr(layer, "LayerThickness") else None
                }
                result["layers"].append(layer_info)
                if layer_info["thickness"]:
                    result["total_thickness"] += layer_info["thickness"]
                    
        # Handle material layer set
        elif material_set.is_a('IfcMaterialLayerSet'):
            for i, layer in enumerate(material_set.MaterialLayers):
                layer_info = {
                    "index": i,
                    "material": layer.Material.Name if layer.Material else "Unknown",
                    "thickness": round(float(layer.LayerThickness), 3) if hasattr(layer, "LayerThickness") else None
                }
                result["layers"].append(layer_info)
                if layer_info["thickness"]:
                    result["total_thickness"] += layer_info["thickness"]
        
        else:
            return json.dumps({
                "error": f"Element {element_guid} does not have material layer information"
            }, indent=2)
            
        result["total_thickness"] = round(result["total_thickness"], 3)
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error analyzing material layers: {str(e)}"
        }, indent=2)

if __name__ == "__main__":
    # Test with some example GUIDs (update these for your model)
    test_guids = [
        "2O2Fr$t4X7Zf8NOew3FNr2",  # Example wall GUID
        "3bXiCStxP6Fgxdej$yc50n",  # Example ceiling GUID
        "invalid_guid"  # Test error handling
    ]
    
    print("\nTesting with example GUIDs:")
    for guid in test_guids:
        print(f"\nGetting material layers for {guid}:")
        print(get_element_material_layers_and_thicknesses(model="arc", element_guid=guid))
    
    # Test with no GUID
    print("\nTesting with no GUID:")
    print(get_element_material_layers_and_thicknesses(model="arc")) 