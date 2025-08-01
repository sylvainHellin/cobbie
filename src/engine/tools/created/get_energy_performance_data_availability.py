
import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any, List
import re

def get_energy_performance_data_availability(ifc_file_path: str) -> Dict[str, Any]:
    """
    Systematically searches an IFC model for all available energy performance-related data 
    and provides a comprehensive report on what information is available and what is missing.
    
    This function works with IFC models exported from various BIM authoring software,
    with special attention to Revit's energy analysis property sets (PSet_Revit_Energy Analysis).
    
    Args:
        ifc_file_path (str): Path to the IFC file to analyze
        
    Returns:
        Dict[str, Any]: A structured dictionary containing:
            - available_data: Energy data found in the model with values and sources
            - missing_data: Energy data that was searched for but not found
            - recommendations: Suggestions for obtaining missing data
            - element_summary: Summary of energy-related elements found
            - property_sets: List of all energy-related property sets identified
    """
    # Initialize result structure
    result = {
        "available_data": {},
        "missing_data": [],
        "recommendations": [],
        "element_summary": {},
        "property_sets": []
    }
    
    # Open the IFC model
    try:
        model = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        result["error"] = f"Failed to open IFC file: {str(e)}"
        return result
    
    # Identify energy-related elements
    building_elements = model.by_type("IfcBuilding")
    space_elements = model.by_type("IfcSpace")
    
    # For energy conversion devices, try specific types since general IfcEnergyConversionDevice might not exist
    energy_conversion_devices = []
    specific_types = ["IfcBoiler", "IfcChiller", "IfcCoil", "IfcCompressor", "IfcCondenser", 
                      "IfcCooledBeam", "IfcCoolingTower", "IfcElectricGenerator", "IfcElectricMotor", 
                      "IfcEvaporativeCooler", "IfcEvaporator", "IfcHeatExchanger", "IfcHumidifier", 
                      "IfcMotorConnection", "IfcSolarDevice", "IfcTransformer", "IfcUnitaryEquipment"]
    
    for type_name in specific_types:
        try:
            devices = model.by_type(type_name)
            energy_conversion_devices.extend(devices)
        except:
            pass
    
    # Update element summary
    result["element_summary"] = {
        "IfcBuilding": len(building_elements),
        "IfcSpace": len(space_elements),
        "EnergyConversionDevices": len(energy_conversion_devices)
    }
    
    # Identify energy-related property sets
    all_property_sets = model.by_type("IfcPropertySet")
    energy_pset_names = []
    
    for pset in all_property_sets:
        if hasattr(pset, 'Name') and pset.Name:
            name_lower = pset.Name.lower()
            if any(keyword in name_lower for keyword in ['energy', 'power', 'thermal', 'heat', 'cool', 'electric', 'performance', 'load', 'analysis']):
                energy_pset_names.append(pset.Name)
                if pset.Name not in result["property_sets"]:
                    result["property_sets"].append(pset.Name)
    
    # Extract specific energy performance metrics
    energy_metrics = {
        "annual_energy_consumption": None,
        "energy_use_intensity": None,
        "design_heating_load": None,
        "design_cooling_load": None,
        "equipment_power_ratings": [],
        "renewable_energy_capacity": None,
        "thermal_transmittance": [],
        "air_leakage_rate": None
    }
    
    # Process property sets for energy data
    for pset in all_property_sets:
        if hasattr(pset, 'Name') and pset.Name and pset.Name in energy_pset_names:
            if hasattr(pset, 'HasProperties'):
                for prop in pset.HasProperties:
                    prop_name = prop.Name if hasattr(prop, 'Name') else 'Unnamed'
                    prop_value = None
                    
                    # Try to get the property value
                    if hasattr(prop, 'NominalValue') and prop.NominalValue:
                        prop_value = prop.NominalValue.wrappedValue if hasattr(prop.NominalValue, 'wrappedValue') else str(prop.NominalValue)
                    
                    # Try to get unit information from various possible locations
                    unit = "unknown"
                    # Check various possible locations for unit information
                    if hasattr(prop.NominalValue, 'Unit'):
                        unit = str(prop.NominalValue.Unit)
                    elif hasattr(prop.NominalValue, 'unit'):
                        unit = str(prop.NominalValue.unit)
                    elif hasattr(prop, 'Unit'):
                        unit = str(prop.Unit)
                    elif hasattr(prop.NominalValue, 'SIUnitName'):
                        unit = str(prop.NominalValue.SIUnitName)
                    
                    # Map properties to energy metrics
                    prop_name_lower = prop_name.lower() if prop_name else ""
                    
                    # Annual energy consumption
                    if any(keyword in prop_name_lower for keyword in ['annual energy', 'energy consumption', 'total energy']):
                        # Only add if value is not None and not 0.0 (which might be a default)
                        if prop_value is not None and (prop_value != 0.0 or 'annual' in prop_name_lower or 'consumption' in prop_name_lower):
                            energy_metrics["annual_energy_consumption"] = {
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            }
                    
                    # Energy Use Intensity (EUI)
                    elif 'eui' in prop_name_lower or 'energy use intensity' in prop_name_lower:
                        if prop_value is not None and prop_value != 0.0:
                            energy_metrics["energy_use_intensity"] = {
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            }
                    
                    # Design heating/cooling loads
                    elif 'heating load' in prop_name_lower or 'heat load' in prop_name_lower:
                        # Only add if value is not None and not 0.0 (which might be a default)
                        if prop_value is not None and prop_value != 0.0:
                            energy_metrics["design_heating_load"] = {
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            }
                    elif 'cooling load' in prop_name_lower:
                        # Only add if value is not None and not 0.0 (which might be a default)
                        if prop_value is not None and prop_value != 0.0:
                            energy_metrics["design_cooling_load"] = {
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            }
                    
                    # Equipment power ratings
                    elif any(keyword in prop_name_lower for keyword in ['power', 'apparent load', 'active power']):
                        if prop_value is not None and prop_value != 0.0:
                            energy_metrics["equipment_power_ratings"].append({
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            })
                    
                    # Renewable energy capacity
                    elif any(keyword in prop_name_lower for keyword in ['renewable', 'solar', 'pv', 'capacity']):
                        if prop_value is not None and prop_value != 0.0:
                            energy_metrics["renewable_energy_capacity"] = {
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            }
                    
                    # Thermal transmittance (U-values)
                    elif any(keyword in prop_name_lower for keyword in ['thermal transmittance', 'u-value', 'u factor']):
                        if prop_value is not None and prop_value != 0.0:
                            energy_metrics["thermal_transmittance"].append({
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            })
                    
                    # Air leakage rates
                    elif any(keyword in prop_name_lower for keyword in ['air leakage', 'infiltration', 'air change']):
                        if prop_value is not None and prop_value != 0.0:
                            energy_metrics["air_leakage_rate"] = {
                                "value": prop_value,
                                "source": f"{pset.Name}.{prop_name}",
                                "unit": unit
                            }
    
    # Check for certification-related data (LEED, BREEAM, etc.)
    certification_data = None
    certification_keywords = ['leed', 'breeam', 'certification', 'rating', 'sustainability']
    
    for pset in all_property_sets:
        if hasattr(pset, 'Name') and pset.Name:
            pset_name_lower = pset.Name.lower()
            if any(keyword in pset_name_lower for keyword in certification_keywords):
                certification_props = {}
                if hasattr(pset, 'HasProperties'):
                    for prop in pset.HasProperties:
                        if hasattr(prop, 'Name') and prop.Name:
                            prop_name_lower = prop.Name.lower()
                            if any(keyword in prop_name_lower for keyword in certification_keywords):
                                if hasattr(prop, 'NominalValue') and prop.NominalValue:
                                    prop_value = prop.NominalValue.wrappedValue if hasattr(prop.NominalValue, 'wrappedValue') else str(prop.NominalValue)
                                    certification_props[prop.Name] = {
                                        "value": prop_value,
                                        "source": f"{pset.Name}.{prop.Name}"
                                    }
                if certification_props:
                    certification_data = certification_props
                    break
    
    # Add certification data to available data if found
    if certification_data:
        result["available_data"]["certification_data"] = certification_data
    
    # Populate available data
    for metric, value in energy_metrics.items():
        if value:
            if isinstance(value, list) and len(value) > 0:
                result["available_data"][metric] = value
            elif isinstance(value, dict) and value.get("value") is not None:
                result["available_data"][metric] = value
            elif value is not None and not (isinstance(value, list) and len(value) == 0):
                result["available_data"][metric] = value
    
    # Identify missing data
    all_metrics = list(energy_metrics.keys())
    for metric in all_metrics:
        if metric not in result["available_data"]:
            result["missing_data"].append(metric)
    
    # Add recommendations based on missing data
    if "annual_energy_consumption" in result["missing_data"]:
        result["recommendations"].append("Annual energy consumption data is missing. Consider performing an energy simulation or adding this information to the model's energy analysis property sets.")
    
    if "energy_use_intensity" in result["missing_data"]:
        result["recommendations"].append("Energy Use Intensity (EUI) data is missing. This can be calculated from total energy consumption and building area, consider adding it to PSet_Revit_Energy Analysis.")
    
    if "design_heating_load" in result["missing_data"] or "design_cooling_load" in result["missing_data"]:
        result["recommendations"].append("HVAC design load information is missing. This information is typically available from energy simulation software and should be added to the model.")
    
    if "renewable_energy_capacity" in result["missing_data"]:
        result["recommendations"].append("Renewable energy capacity data is missing. If the building has renewable energy systems, consider adding this information to the model.")
    
    if "air_leakage_rate" in result["missing_data"]:
        result["recommendations"].append("Air leakage rate data is missing. This information is important for energy analysis and can be obtained from blower door tests or energy simulations.")
    
    if not result["property_sets"]:
        result["recommendations"].append("No energy-related property sets were found. Consider adding energy analysis data to the model using appropriate property sets like PSet_Revit_Energy Analysis.")
    
    # Add recommendation if no certification data found
    if not certification_data:
        result["recommendations"].append("No certification-related data (LEED, BREEAM, etc.) was found. If the building has sustainability certifications, consider adding this information to the model.")
    
    return result
