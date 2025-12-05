# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import json

def analyze_elements_exterior_classification(model_path: str, element_guids: list[str] | None = None) -> str:
    """Determines which elements from a list face the exterior.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        element_guids (list[str]): List of element Global IDs to check
            Example: ["2O2Fr$t4X7Zf8NOew3FNhv", "3hKe29vjL9pPkxwvnQ$KUw"]
                
    Returns:
        str: JSON string containing:
            {
                "total_exterior": Count of exterior elements,
                "total_interior": Count of interior elements,
                "elements": [
                    {
                        "guid": Element's Global ID,
                        "name": Element name if available,
                        "type": IFC class of the element,
                        "is_exterior": Boolean indicating if element faces exterior
                    },
                    ...
                ],
                "errors": Array of any GUIDs that couldn't be processed
            }
    """
    if not element_guids:
        return json.dumps({"error": "No element GUIDs provided"}, indent=2)

    ifc_model = ifcopenshell.open(model_path)
    
    try:
        # Initialize results structure
        result = {
            "total_exterior": 0,
            "total_interior": 0,
            "elements": [],
            "errors": []
        }
        
        for guid in element_guids:
            try:
                # Get element by GUID
                element = ifc_model.by_guid(guid)
                if not element:
                    result["errors"].append({
                        "guid": guid,
                        "error": "Element not found"
                    })
                    continue
                
                is_exterior = False
                # Get element relationships
                element_rels = ifc_model.get_inverse(element)
                
                for rel in element_rels:
                    # Check for material/layer associations
                    if rel.is_a("IfcRelAssociatesMaterial"):
                        material = rel.RelatingMaterial
                        # Check if material or layer set indicates exterior
                        if material.is_a("IfcMaterialLayerSet"):
                            for layer in material.MaterialLayers:
                                if layer.Name and "exterior" in layer.Name.lower():
                                    is_exterior = True
                                    break
                                    
                    # Check for property sets
                    elif rel.is_a("IfcRelDefinesByProperties"):
                        pset = rel.RelatingPropertyDefinition
                        if pset.is_a("IfcPropertySet"):
                            for prop in pset.HasProperties:
                                # Look for properties indicating exterior
                                if prop.Name and "IsExternal" in prop.Name:
                                    if hasattr(prop, "NominalValue") and prop.NominalValue.wrappedValue:
                                        is_exterior = True
                                        break
                    
                    if is_exterior:
                        break
                
                # Add element info to results
                element_info = {
                    "guid": guid,
                    "name": element.Name if hasattr(element, "Name") else "Unnamed",
                    "type": element.is_a(),
                    "is_exterior": is_exterior
                }
                result["elements"].append(element_info)

                # Update totals using local variables with proper typing
                total_exterior: int = result["total_exterior"]  # type: ignore
                total_interior: int = result["total_interior"]  # type: ignore
                if is_exterior:
                    total_exterior = total_exterior + 1
                else:
                    total_interior = total_interior + 1
                result["total_exterior"] = total_exterior
                result["total_interior"] = total_interior
                    
            except Exception as e:
                result["errors"].append({
                    "guid": guid,
                    "error": str(e)
                })
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error checking exterior elements: {str(e)}"
        }, indent=2) 