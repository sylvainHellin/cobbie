# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.system
import ifcopenshell.util.shape
import ifcopenshell.geom
import json

def get_pipe_length_by_type(model_path: str, pipe_types: list[str] | None = None, depth: int = 2) -> str:
    """Calculates the total length of pipes in the model that match specified type names.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
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

    ifc_model = ifcopenshell.open(model_path)
    
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
                    geom = shape.geometry()
                    length = ifcopenshell.util.shape.get_total_edge_length(geom)

                    # Update total length using local variable
                    total = result["total_length"]
                    total += length
                    result["total_length"] = total

                    # Update type breakdown if depth >= 1
                    if depth >= 1:
                        type_breakdown: dict = result["type_breakdown"]  # type: ignore
                        if matched_type not in type_breakdown:
                            type_breakdown[matched_type] = 0.0
                        current_val: float = type_breakdown[matched_type]  # type: ignore
                        current_val = current_val + length
                        type_breakdown[matched_type] = current_val
                        result["type_breakdown"] = type_breakdown
                    
                    # Add detailed pipe info if depth >= 2
                    if depth >= 2:
                        pipe_info = {
                            "id": pipe.id(),
                            "name": pipe.Name if hasattr(pipe, "Name") else "Unnamed",
                            "type": matched_type,
                            "length": round(length, 3)
                        }
                        result["matching_pipes"].append(pipe_info)
                        count = result["total_count"]
                        count += 1
                        result["total_count"] = count
                    
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