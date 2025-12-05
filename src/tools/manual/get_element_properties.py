# python packages
import json

# ifcopenshell
import ifcopenshell

def extract_quantity_from_property_sets(properties):
    """Helper function to extract quantities from property sets"""
    quantity_psets = {
        "PSet_Revit_Dimensions",
        "BaseQuantities",
        "ArchiCADQuantities",
        "Qto_WallBaseQuantities",
        "Qto_DoorBaseQuantities",
        # Add other quantity property set names as needed
    }
    
    quantities = {}
    for pset_name, props in properties["property_sets"].items():
        if pset_name in quantity_psets:
            quantities[pset_name] = {
                name: {
                    "value": float(value) if isinstance(value, str) and value.replace(".", "").isdigit() else value,
                    "unit": None  # Units could be inferred based on property name if needed
                }
                for name, value in props.items()
                if value is not None
            }
    return quantities

def get_element_properties(model_path: str, element_guid: str | None = None) -> str:
    """Gets detailed properties for a specific element including dimensions if available.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        element_guid (str, optional): The GUID of the element to get properties for
            Example: "2O2Fr$t4X7Zf8NOew3FNhv"
            
    Returns:
        str: JSON string containing:
            {
                "guid": Element's Global ID,
                "name": Element name if available,
                "type": IFC class of the element,
                "description": Element description if available,
                "property_sets": {
                    "Pset_Name1": {
                        "property1": "value1",
                        "property2": "value2",
                        ...
                    },
                    ...
                },
                "quantities": {
                    "BaseQuantities": {
                        "Length": 1.0,
                        "Area": 2.0,
                        ...
                    },
                    "PSet_Revit_Dimensions": {
                        "Length": 1.0,
                        "Width": 2.0,
                        ...
                    }
                }
            }
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

        # Get basic element info
        properties = {
            "guid": element.GlobalId,
            "name": element.Name if element.Name else "Unnamed",
            "type": element.is_a(),
            "description": element.Description if hasattr(element, "Description") else None,
            "property_sets": {},
            "quantities": {}
        }

        # Get property sets
        for definition in element.IsDefinedBy:
            if definition.is_a("IfcRelDefinesByProperties"):
                property_set = definition.RelatingPropertyDefinition
                
                # Handle regular property sets
                if property_set.is_a("IfcPropertySet"):
                    props = {}
                    for prop in property_set.HasProperties:
                        if prop.is_a("IfcPropertySingleValue"):
                            props[prop.Name] = str(prop.NominalValue.wrappedValue) if prop.NominalValue else None
                    properties["property_sets"][property_set.Name] = props
                
                # Handle traditional quantity sets
                elif property_set.is_a("IfcElementQuantity"):
                    quantities = {}
                    for quantity in property_set.Quantities:
                        if hasattr(quantity, 'is_a'):
                            q_type = quantity.is_a()
                            if q_type in ["IfcQuantityLength", "IfcQuantityArea", "IfcQuantityVolume", "IfcQuantityCount", "IfcQuantityWeight"]:
                                value = None
                                if q_type == "IfcQuantityLength":
                                    value = quantity.LengthValue
                                elif q_type == "IfcQuantityArea":
                                    value = quantity.AreaValue
                                elif q_type == "IfcQuantityVolume":
                                    value = quantity.VolumeValue
                                elif q_type == "IfcQuantityCount":
                                    value = quantity.CountValue
                                elif q_type == "IfcQuantityWeight":
                                    value = quantity.WeightValue
                                quantities[quantity.Name] = value
                    if quantities:
                        properties["quantities"][property_set.Name] = quantities

        # Extract quantities from property sets
        quantity_properties = extract_quantity_from_property_sets(properties)
        if quantity_properties:
            properties["quantities"].update(quantity_properties)

        return json.dumps(properties, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Error getting element properties: {str(e)}"
        }, indent=2) 