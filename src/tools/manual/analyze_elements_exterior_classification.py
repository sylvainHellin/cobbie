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

def analyze_elements_exterior_classification(model: str = None, element_guids: list[str] = None) -> str:
    """Determines which elements from a list face the exterior.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
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
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
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
                
                # Update totals
                if is_exterior:
                    result["total_exterior"] += 1
                else:
                    result["total_interior"] += 1
                    
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

if __name__ == "__main__":
    # Test with some example GUIDs (update these for your model)
    test_guids = [
        "1hOSvn6df7F8_7GcBWlRGQ",  # Example door GUID
        "1hOSvn6df7F8_7GcBWlSDm",  # Example window GUID
        "invalid_guid"  # Test error handling
    ]
    
    print("\nAnalyzing elements in architectural model:")
    print(analyze_elements_exterior_classification(model="arc", element_guids=test_guids))
    
    # Test with empty list
    print("\nTesting with empty GUID list:")
    print(analyze_elements_exterior_classification(model="arc", element_guids=[])) 