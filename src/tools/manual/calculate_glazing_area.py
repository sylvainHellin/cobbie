# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def calculate_glazing_area(model_path: str) -> str:
    """Calculates the total glazing area of all windows in the model.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.

    Returns:
        str: A string containing:
            - Total glazing area in square meters (rounded to 2 decimal places)
            - Note if the area includes frame area
            - Error message if calculation fails
    """
    ifc_model = ifcopenshell.open(model_path)
    
    try:
        # Get all windows in the model
        windows = ifc_model.by_type("IfcWindow")
        
        if not windows:
            return "No windows found in model"
        
        total_glazing_area = 0
        total_window_area = 0
        
        for window in windows:
            # Get window dimensions
            height = getattr(window, "OverallHeight", None)
            width = getattr(window, "OverallWidth", None)
            
            if not height or not width:
                # Try to get dimensions from window type if not directly on window
                window_type = ifcopenshell.util.element.get_type(window)
                if window_type:
                    height = getattr(window_type, "OverallHeight", 0)
                    width = getattr(window_type, "OverallWidth", 0)
            
            if height and width:
                # Calculate total window area
                window_area = float(height) * float(width)
                total_window_area += window_area
                
                # Check for frame thickness
                frame_props = None
                if hasattr(window, "IsTypedBy") and window.IsTypedBy:
                    window_type = window.IsTypedBy[0].RelatingType
                    if hasattr(window_type, "HasPropertySets"):
                        for pset in window_type.HasPropertySets:
                            if pset.is_a("IfcWindowPanelProperties"):
                                frame_props = pset
                                break
                
                if frame_props:
                    frame_width = getattr(frame_props, "FrameThickness", 0)
                    if frame_width:
                        # Subtract frame area (approximate as frame width * perimeter)
                        frame_area = float(frame_width) * (2 * float(height) + 2 * float(width))
                        window_area -= frame_area
                        total_glazing_area += window_area
                    else:
                        total_glazing_area += window_area
                else:
                    total_glazing_area += window_area
        
        if total_glazing_area == total_window_area:
            return f"{round(total_glazing_area, 2)} m² (total window area, frame areas could not be determined)"
        else:
            return f"{round(total_glazing_area, 2)} m² (glazing area only, frame areas subtracted)"
        
    except Exception as e:
        return f"Error calculating glazing area: {str(e)}" 