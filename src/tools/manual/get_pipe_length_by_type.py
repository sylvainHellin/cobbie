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
import ifcopenshell.util.system
import ifcopenshell.util.shape
import ifcopenshell.geom

def get_pipe_length_by_type(model: str = None, pipe_types: list[str] = None, depth: int = 2) -> str:
    """Calculates the total length of pipes in the model that match specified type names.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        pipe_types (list[str]): List of type names to search for in pipe properties 
            (e.g. ['cold water', 'hot water', 'waste'])
        depth (int, optional): Level of detail in the results:
            0: Only total length for all types
            1: Total length + breakdown by type
            2: Complete details including individual pipe segments
            
    Returns:
        str: JSON string containing:
            depth 0: {
                "total_length": Total length in meters
            }
            depth 1: {
                "total_length": Total length in meters,
                "type_breakdown": {
                    "type1": length1,
                    "type2": length2,
                    ...
                }
            }
            depth 2: {
                "total_length": Total length in meters,
                "type_breakdown": {...},
                "matching_pipes": [
                    {
                        "id": Pipe ID,
                        "name": Pipe name,
                        "type": Matched type,
                        "length": Length in meters
                    },
                    ...
                ],
                "total_count": Number of matching pipes
            }
    """
    if not pipe_types:
        return json.dumps({"error": "No pipe types provided"}, indent=2)
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    try:
        pipes = ifc_model.by_type("IfcFlowSegment")
        if not pipes:
            return json.dumps({"error": "No pipe segments found in model"}, indent=2)
        
        # Initialize result based on depth
        result = {"total_length": 0.0}
        if depth >= 1:
            result["type_breakdown"] = {}
        if depth >= 2:
            result["matching_pipes"] = []
            result["total_count"] = 0
        
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        for pipe in pipes:
            # Get all searchable text from pipe properties
            searchable_text = []
            
            pipe_type = ifcopenshell.util.element.get_type(pipe)
            if pipe_type:
                searchable_text.extend([pipe_type.Name or "", pipe_type.Description or ""])
            
            searchable_text.extend([pipe.Name or "", pipe.Description or ""])
            
            # Add property set values
            psets = ifcopenshell.util.element.get_psets(pipe)
            for props in psets.values():
                searchable_text.extend(str(value) for value in props.values())
            
            # Add system info
            for system in ifcopenshell.util.system.get_element_systems(pipe):
                searchable_text.extend([
                    system.Name or "",
                    system.Description or "",
                    system.PredefinedType or ""
                ])
            
            # Check if pipe matches any type
            combined_text = " ".join(searchable_text).lower()
            matched_type = None
            for pipe_type in pipe_types:
                if pipe_type.lower() in combined_text:
                    matched_type = pipe_type
                    break
            
            if matched_type:
                try:
                    shape = ifcopenshell.geom.create_shape(settings, pipe)
                    length = ifcopenshell.util.shape.get_total_edge_length(shape.geometry)
                    
                    # Update total length
                    result["total_length"] += length
                    
                    # Update type breakdown if depth >= 1
                    if depth >= 1:
                        if matched_type not in result["type_breakdown"]:
                            result["type_breakdown"][matched_type] = 0
                        result["type_breakdown"][matched_type] += length
                    
                    # Add detailed pipe info if depth >= 2
                    if depth >= 2:
                        pipe_info = {
                            "id": pipe.id(),
                            "name": pipe.Name if hasattr(pipe, "Name") else "Unnamed",
                            "type": matched_type,
                            "length": round(length, 3)
                        }
                        result["matching_pipes"].append(pipe_info)
                        result["total_count"] += 1
                    
                except RuntimeError:
                    continue
        
        # Round values
        result["total_length"] = round(result["total_length"], 3)
        if depth >= 1:
            result["type_breakdown"] = {k: round(v, 3) for k, v in result["type_breakdown"].items()}
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error calculating pipe lengths: {str(e)}"
        }, indent=2)

if __name__ == "__main__":
    # Test with common pipe types
    pipe_types = ["Mechanical Pipe", "Cold Water", "Hot Water", "Waste", "PVC"]
    
    print("\nAnalyzing pipe lengths in MEP model (depth=0):")
    print(get_pipe_length_by_type(model="mep", pipe_types=pipe_types, depth=0))
    
    print("\nAnalyzing pipe lengths in MEP model (depth=1):")
    print(get_pipe_length_by_type(model="mep", pipe_types=pipe_types, depth=1))
    
    print("\nAnalyzing pipe lengths in MEP model (depth=2):")
    print(get_pipe_length_by_type(model="mep", pipe_types=pipe_types, depth=2))
    
    # Test with architectural model (shouldn't have pipes)
    print("\nTesting with architectural model:")
    print(get_pipe_length_by_type(model="arc", pipe_types=pipe_types))
    
    # Test with empty list
    print("\nTesting with empty pipe types list:")
    print(get_pipe_length_by_type(model="mep", pipe_types=[])) 