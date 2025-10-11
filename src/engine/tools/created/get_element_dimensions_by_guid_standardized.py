import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *


def get_element_dimensions_by_guid_standardized(model_path: str, guid: str) -> Dict[str, Any]:
    """
    Retrieve standardized dimensional properties of an IFC element by its GlobalId.
    
    This function searches across multiple property sets and direct attributes to extract
    dimensional properties and returns them in a standardized format with consistent naming.
    
    Args:
        model_path: Path to the IFC file
        guid: GlobalId of the element to analyze
        
    Returns:
        Dictionary containing standardized dimensional properties:
        {
            'width': {'value': float, 'confidence': str, 'source': str},
            'height': {'value': float, 'confidence': str, 'source': str},
            'thickness': {'value': float, 'confidence': str, 'source': str},
            'length': {'value': float, 'confidence': str, 'source': str},
            'area': {'value': float, 'confidence': str, 'source': str},
            'volume': {'value': float, 'confidence': str, 'source': str},
            'element_type': str,
            'element_name': str
        }
        
    Notes:
        - This function handles both Revit and ArchiCAD property sets
        - Returns None for missing dimensions rather than failing
        - Confidence levels: 'high' (from quantities), 'medium' (from standard property sets),
          'low' (from calculated or indirect sources)
        - All dimensions are returned in meters (SI units)
    """
    
    # Initialize result dictionary
    result = {
        'width': {'value': None, 'confidence': None, 'source': None},
        'height': {'value': None, 'confidence': None, 'source': None},
        'thickness': {'value': None, 'confidence': None, 'source': None},
        'length': {'value': None, 'confidence': None, 'source': None},
        'area': {'value': None, 'confidence': None, 'source': None},
        'volume': {'value': None, 'confidence': None, 'source': None},
        'element_type': None,
        'element_name': None
    }
    
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
        
        # Find element by GUID
        element = model.by_guid(guid)
        if not element:
            return result
            
        result['element_type'] = element.is_a()
        result['element_name'] = getattr(element, 'Name', None)
        
        # Define property mappings for different naming conventions
        property_mappings = {
            'width': [
                # English names
                'Width', 'OverallWidth', 'ClearWidth', 'NominalWidth',
                # German names (ArchiCAD)
                'Breite', 'Gesamtbreite', 'lichte Breite', 'Nennbreite'
            ],
            'height': [
                # English names
                'Height', 'OverallHeight', 'ClearHeight', 'NominalHeight',
                # German names (ArchiCAD)
                'Höhe', 'Gesamthöhe', 'lichte Höhe', 'Nennhöhe'
            ],
            'thickness': [
                # English names
                'Thickness', 'Depth', 'WallThickness',
                # German names (ArchiCAD)
                'Dicke', 'Tiefe', 'Wandstärke'
            ],
            'length': [
                # English names
                'Length', 'OverallLength', 'ClearLength', 'NominalLength',
                # German names (ArchiCAD)
                'Länge', 'Gesamtlänge', 'lichte Länge', 'Nennlänge'
            ],
            'area': [
                # English names
                'Area', 'GrossArea', 'NetArea', 'SurfaceArea', 'FootprintArea',
                # German names (ArchiCAD)
                'Fläche', 'Bruttofläche', 'Nettofläche', 'Oberfläche', 'Grundfläche'
            ],
            'volume': [
                # English names
                'Volume', 'GrossVolume', 'NetVolume',
                # German names (ArchiCAD)
                'Volumen', 'Bruttovolumen', 'Nettovolumen'
            ]
        }
        
        # Priority order for property sets (highest to lowest confidence)
        priority_sets = [
            'BaseQuantities',           # High confidence - standard quantities
            'ArchiCADQuantities',       # High confidence - ArchiCAD specific
            'Pset_Revit_Dimensions',    # Medium confidence - Revit specific
            'Pset_Revit_Type_Dimensions', # Medium confidence - Revit type specific
            'Pset_DoorCommon',          # Medium confidence - standard door props
            'Pset_WindowCommon',        # Medium confidence - standard window props
            'Pset_WallCommon',          # Medium confidence - standard wall props
            'Pset_SlabCommon',          # Medium confidence - standard slab props
            'Pset_BeamCommon',          # Medium confidence - standard beam props
            'Pset_ColumnCommon'         # Medium confidence - standard column props
        ]
        
        # Helper function to extract value from quantity object
        def extract_quantity_value(quantity):
            """Extract numeric value from different quantity types"""
            if hasattr(quantity, 'LengthValue'):
                return quantity.LengthValue
            elif hasattr(quantity, 'AreaValue'):
                return quantity.AreaValue
            elif hasattr(quantity, 'VolumeValue'):
                return quantity.VolumeValue
            elif hasattr(quantity, 'CountValue'):
                return quantity.CountValue
            return None
        
        # Helper function to extract value from property object
        def extract_property_value(prop):
            """Extract numeric value from property objects"""
            if hasattr(prop, 'NominalValue'):
                nominal_value = prop.NominalValue
                # Handle wrapped values (e.g., IfcLengthMeasure)
                if hasattr(nominal_value, 'wrappedValue'):
                    return nominal_value.wrappedValue
                elif hasattr(nominal_value, '__float__'):
                    return float(nominal_value)
                else:
                    return nominal_value
            return None
        
        # Search through property sets and quantities
        found_properties = set()  # Track which properties we've already found
        
        # Get all property relationships
        property_relations = []
        if hasattr(element, 'IsDefinedBy'):
            property_relations = element.IsDefinedBy
        
        # Sort property sets by priority
        sorted_sets = []
        for rel in property_relations:
            if hasattr(rel, 'RelatingPropertyDefinition'):
                prop_def = rel.RelatingPropertyDefinition
                if hasattr(prop_def, 'Name'):
                    set_name = prop_def.Name
                    # Find priority index (lower = higher priority)
                    priority = len(priority_sets)
                    if set_name in priority_sets:
                        priority = priority_sets.index(set_name)
                    sorted_sets.append((priority, set_name, prop_def))
        
        # Sort by priority (lower index first)
        sorted_sets.sort(key=lambda x: x[0])
        
        # Process each property set in priority order
        for priority, set_name, prop_def in sorted_sets:
            # Skip if we've already found all properties
            if len(found_properties) >= len(property_mappings):
                break
                
            if hasattr(prop_def, 'is_a'):
                if prop_def.is_a() == 'IfcElementQuantity':
                    # Process quantities
                    if hasattr(prop_def, 'Quantities'):
                        for quant in prop_def.Quantities:
                            if hasattr(quant, 'Name'):
                                quant_name = quant.Name
                                value = extract_quantity_value(quant)
                                
                                # Check if this quantity matches any of our target properties
                                for prop_name, aliases in property_mappings.items():
                                    if prop_name not in found_properties and quant_name in aliases:
                                        if value is not None:
                                            result[prop_name] = {
                                                'value': float(value),
                                                'confidence': 'high',
                                                'source': f'{set_name}.{quant_name}'
                                            }
                                            found_properties.add(prop_name)
                                            
                elif prop_def.is_a() == 'IfcPropertySet':
                    # Process property sets
                    if hasattr(prop_def, 'HasProperties'):
                        for prop in prop_def.HasProperties:
                            if hasattr(prop, 'Name'):
                                prop_name = prop.Name
                                value = extract_property_value(prop)
                                
                                # Check if this property matches any of our target properties
                                for target_prop, aliases in property_mappings.items():
                                    if target_prop not in found_properties and prop_name in aliases:
                                        if value is not None:
                                            try:
                                                numeric_value = float(value)
                                                confidence = 'medium' if 'Pset_' in set_name else 'low'
                                                result[target_prop] = {
                                                    'value': numeric_value,
                                                    'confidence': confidence,
                                                    'source': f'{set_name}.{prop_name}'
                                                }
                                                found_properties.add(target_prop)
                                            except (ValueError, TypeError):
                                                pass
        
        # Calculate derived properties if not found directly
        element_type = result['element_type']
        
        # Calculate area from length and height for walls if not found
        if (element_type in ['IfcWall', 'IfcWallStandardCase'] and 
            result['area']['value'] is None and 
            result['length']['value'] is not None and 
            result['height']['value'] is not None):
            
            calculated_area = result['length']['value'] * result['height']['value']
            result['area'] = {
                'value': calculated_area,
                'confidence': 'low',
                'source': 'calculated_from_length_height'
            }
        
        # Calculate volume from area and thickness for walls if not found
        if (element_type in ['IfcWall', 'IfcWallStandardCase'] and 
            result['volume']['value'] is None and 
            result['area']['value'] is not None and 
            result['thickness']['value'] is not None):
            
            calculated_volume = result['area']['value'] * result['thickness']['value']
            result['volume'] = {
                'value': calculated_volume,
                'confidence': 'low',
                'source': 'calculated_from_area_thickness'
            }
        
        # For doors and windows, use width and height to calculate area if not found
        if (element_type in ['IfcDoor', 'IfcWindow'] and 
            result['area']['value'] is None and 
            result['width']['value'] is not None and 
            result['height']['value'] is not None):
            
            calculated_area = result['width']['value'] * result['height']['value']
            result['area'] = {
                'value': calculated_area,
                'confidence': 'low',
                'source': 'calculated_from_width_height'
            }
        
        # For slabs, calculate area if not found and thickness is available
        if (element_type == 'IfcSlab' and 
            result['area']['value'] is None and 
            result['volume']['value'] is not None and 
            result['thickness']['value'] is not None and 
            result['thickness']['value'] > 0):
            
            calculated_area = result['volume']['value'] / result['thickness']['value']
            result['area'] = {
                'value': calculated_area,
                'confidence': 'low',
                'source': 'calculated_from_volume_thickness'
            }
        
        return result
        
    except Exception as e:
        # Return partial results if error occurs
        result['error'] = str(e)
        return result