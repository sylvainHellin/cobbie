
import ifcopenshell
from typing import Optional, Dict, Any, List
import json

def get_floor_to_floor_heights_comprehensive(
    ifc_file_path: str,
    from_storey_name: Optional[str] = None,
    to_storey_name: Optional[str] = None,
    include_storey_names: bool = False
) -> Dict[str, Any]:
    """
    Calculate floor-to-floor heights in an IFC model.
    
    This function can operate in two modes:
    1. If from_storey_name and to_storey_name are None: Returns heights between all consecutive building storeys
    2. If from_storey_name and to_storey_name are provided: Returns height between those specific storeys
    
    Parameters:
    - ifc_file_path (str): Path to the IFC file
    - from_storey_name (Optional[str]): Name of the lower storey (if None, return all consecutive heights)
    - to_storey_name (Optional[str]): Name of the upper storey (required if from_storey_name is provided)
    - include_storey_names (bool): Whether to include a list of all storey names in the result
    
    Returns:
    - Dict[str, Any]: A dictionary containing:
      - "results": Either a list of dictionaries (for all heights) or a single dictionary (for specific height)
      - "success": Boolean indicating if the operation was successful
      - "message": Informative message about the result or any errors
      - "storey_names": Optional list of all storey names in the model (if include_storey_names is True)
    """
    try:
        # Open the IFC file
        model = ifcopenshell.open(ifc_file_path)
        
        # Get all IfcBuildingStorey entities
        storeys = model.by_type("IfcBuildingStorey")
        
        # Extract storey information with elevations
        storey_data = []
        storey_names = []
        for storey in storeys:
            name = storey.Name if storey.Name else "Unnamed Storey"
            elevation = getattr(storey, 'Elevation', None)
            storey_data.append({
                'name': name,
                'elevation': elevation
            })
            storey_names.append(name)
        
        # Sort storeys by elevation
        storey_data.sort(key=lambda x: x['elevation'] if x['elevation'] is not None else float('-inf'))
        
        # Prepare response structure
        response = {
            "success": False,
            "message": "",
            "results": None
        }
        
        if include_storey_names:
            response["storey_names"] = storey_names
        
        # Mode 1: Get all consecutive floor-to-floor heights
        if from_storey_name is None and to_storey_name is None:
            # Check if we have enough storeys
            if len(storey_data) < 2:
                response["message"] = "Not enough storeys with elevation data to calculate floor-to-floor heights"
                response["results"] = []
                return response
            
            # Calculate floor-to-floor heights between consecutive storeys
            results = []
            valid_storey_count = 0
            
            for i in range(len(storey_data) - 1):
                from_storey = storey_data[i]
                to_storey = storey_data[i + 1]
                
                # Skip storeys without elevation data
                if from_storey['elevation'] is None or to_storey['elevation'] is None:
                    continue
                
                height = to_storey['elevation'] - from_storey['elevation']
                valid_storey_count += 1
                
                results.append({
                    "from_storey": from_storey['name'],
                    "to_storey": to_storey['name'],
                    "height": height,
                    "from_elevation": from_storey['elevation'],
                    "to_elevation": to_storey['elevation'],
                    "unit": "meters"
                })
            
            response["results"] = results
            response["success"] = True
            response["message"] = f"Successfully calculated {len(results)} floor-to-floor heights"
            
            return response
        
        # Mode 2: Get specific floor-to-floor height between two named storeys
        elif from_storey_name is not None and to_storey_name is not None:
            # Find the specified storeys by name
            from_storey = None
            to_storey = None
            
            for storey in storey_data:
                if storey['name'] == from_storey_name:
                    from_storey = storey
                if storey['name'] == to_storey_name:
                    to_storey = storey
            
            # Check if both storeys were found
            if not from_storey:
                response["message"] = f"Storey '{from_storey_name}' not found in the model. Available storey names: {storey_names}"
                response["results"] = {}
                return response
            
            if not to_storey:
                response["message"] = f"Storey '{to_storey_name}' not found in the model. Available storey names: {storey_names}"
                response["results"] = {}
                return response
            
            # Check if elevations exist
            if from_storey['elevation'] is None:
                response["message"] = f"No elevation data found for storey '{from_storey_name}'"
                response["results"] = {}
                return response
            
            if to_storey['elevation'] is None:
                response["message"] = f"No elevation data found for storey '{to_storey_name}'"
                response["results"] = {}
                return response
            
            # Calculate height difference
            height = to_storey['elevation'] - from_storey['elevation']
            
            # Prepare result
            result = {
                "height": height,
                "from_storey": from_storey_name,
                "to_storey": to_storey_name,
                "from_elevation": from_storey['elevation'],
                "to_elevation": to_storey['elevation'],
                "unit": "meters"
            }
            
            response["results"] = result
            response["success"] = True
            response["message"] = f"Successfully calculated floor-to-floor height between '{from_storey_name}' and '{to_storey_name}'"
            
            # Check if the from_storey is actually below the to_storey
            if height < 0:
                response["message"] += f". Note: '{from_storey_name}' is above '{to_storey_name}'. Negative height indicates reversed order."
            
            return response
        
        # Invalid parameter combination
        else:
            response["message"] = "Invalid parameter combination. Either provide both from_storey_name and to_storey_name, or neither."
            response["results"] = []
            return response
    
    except Exception as e:
        response = {
            "success": False,
            "message": f"Error processing IFC file: {str(e)}",
            "results": []
        }
        if include_storey_names:
            response["storey_names"] = []
        return response
