# python packages
import json

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def get_element_material_layers_and_thicknesses(model_path: str, element_guid: str | None = None) -> str:
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
        model_path (str): Absolute path to the IFC model file to analyze.
        element_guid (str, optional): The Global ID of the IFC element to analyze
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
    
    ifc_model = ifcopenshell.open(model_path)
    
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
            
        layers: list[dict[str, str | int | float | None]] = []
        total_thickness = 0.0

        # Handle material layer set usage
        if material_set.is_a('IfcMaterialLayerSetUsage'):
            layer_set = material_set.ForLayerSet
            for i, layer in enumerate(layer_set.MaterialLayers):
                thickness = round(float(layer.LayerThickness), 3) if hasattr(layer, "LayerThickness") else None
                layer_info: dict[str, str | int | float | None] = {
                    "index": i,
                    "material": layer.Material.Name if layer.Material else "Unknown",
                    "thickness": thickness
                }
                layers.append(layer_info)
                if thickness:
                    total_thickness += thickness

        # Handle material layer set
        elif material_set.is_a('IfcMaterialLayerSet'):
            for i, layer in enumerate(material_set.MaterialLayers):
                thickness = round(float(layer.LayerThickness), 3) if hasattr(layer, "LayerThickness") else None
                layer_info: dict[str, str | int | float | None] = {
                    "index": i,
                    "material": layer.Material.Name if layer.Material else "Unknown",
                    "thickness": thickness
                }
                layers.append(layer_info)
                if thickness:
                    total_thickness += thickness

        else:
            return json.dumps({
                "error": f"Element {element_guid} does not have material layer information"
            }, indent=2)

        result = {
            "element_type": element.is_a(),
            "element_name": element.Name if element.Name else "Unnamed",
            "total_thickness": round(total_thickness, 3),
            "layers": layers
        }
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error analyzing material layers: {str(e)}"
        }, indent=2) 