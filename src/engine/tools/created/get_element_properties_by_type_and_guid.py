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


def get_element_properties_by_type_and_guid(
    model_path: str,
    element_guid: str,
    element_type: str,
    property_categories: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Retrieve and extract standardized properties from an IFC element based on its type.
    
    This function combines element retrieval with intelligent property extraction,
    standardizing property names across different BIM software exports and providing
    confidence levels for extracted data.
    
    Args:
        model_path: Path to the IFC model file
        element_guid: GlobalId of the element to retrieve
        element_type: IFC entity type (e.g., 'IfcDoor', 'IfcWall', 'IfcColumn')
        property_categories: Categories of properties to extract
                           (e.g., ['dimensions', 'fire_rating', 'materials'])
                           If None, extracts all available categories
    
    Returns:
        Dictionary containing:
        - element_info: Basic element details (name, guid, type)
        - dimensions: Standardized dimensional properties
        - fire_rating: Fire rating information if available
        - materials: Material information if available
        - type_classification: Element type-specific classification
        - confidence_level: Confidence in extracted data (0-100)
        - property_sources: Source information for each property
    
    Note:
        This function handles different IFC entity types that might represent the same
        building component (e.g., columns represented as IfcBeam or IfcMember).
        It standardizes property names across different BIM software exports,
        particularly handling ArchiCAD-specific property sets and German property names.
        The function is designed to work with models exported from ArchiCAD and other
        BIM software that use standard IFC property sets.
    """
    
    # Initialize result structure
    result = {
        'element_info': {},
        'dimensions': {},
        'fire_rating': {},
        'materials': {},
        'type_classification': {},
        'confidence_level': 0,
        'property_sources': {}
    }
    
    def _extract_dimensions(element, psets, confidence_tracker, source_tracker):
        """Extract standardized dimensional properties based on element type."""
        dimensions = {}
        element_type = element.is_a()
        
        # Common dimension mappings for different property sets (including German names)
        dimension_mappings = {
            'width': ['Width', 'Breite', 'Thickness', 'Dicke', 'Paneelbreite', 'Rahmen Breite', 'Durchgangslichte Breite'],
            'height': ['Height', 'Höhe', 'Depth', 'Tiefe', 'Türblatt Höhe', 'Rahmen Höhe', 'Durchgangslichte Höhe'],
            'length': ['Length', 'Länge', 'Wandlänge an der Außenseite', 'Wandlänge an der Innenseite', 'Länge der Wand in der Achse'],
            'thickness': ['Thickness', 'Dicke', 'Width', 'Breite', 'Rahmen-Dicke', 'Türblatt Stärke', 'Wanddicke'],
            'depth': ['Depth', 'Tiefe', 'Height', 'Höhe', 'PanelDepth', 'LiningDepth', 'Einfassung Dicke']
        }
        
        # Extract from BaseQuantities (most reliable)
        if 'BaseQuantities' in psets:
            base_quantities = psets['BaseQuantities']
            for standard_name, variants in dimension_mappings.items():
                for variant in variants:
                    if variant in base_quantities:
                        dimensions[standard_name] = base_quantities[variant]
                        confidence_tracker[f'dimensions.{standard_name}'] = 90
                        source_tracker[f'dimensions.{standard_name}'] = 'BaseQuantities'
                        break
        
        # Extract from type-specific common property sets
        common_psets = {
            'IfcWall': 'Pset_WallCommon',
            'IfcWallStandardCase': 'Pset_WallCommon',
            'IfcDoor': 'Pset_DoorCommon', 
            'IfcWindow': 'Pset_WindowCommon',
            'IfcBeam': 'Pset_BeamCommon',
            'IfcSlab': 'Pset_SlabCommon',
            'IfcMember': 'Pset_BeamCommon'  # Members often use beam properties
        }
        
        if element_type in common_psets and common_psets[element_type] in psets:
            common_props = psets[common_psets[element_type]]
            # Add any additional dimensions not found in BaseQuantities
            for prop_name, prop_value in common_props.items():
                if any(dim in prop_name.lower() for dim in ['width', 'height', 'length', 'thickness', 'depth', 'breite', 'höhe', 'länge', 'dicke', 'tiefe']):
                    standard_name = _standardize_dimension_name(prop_name)
                    if standard_name not in dimensions:
                        dimensions[standard_name] = prop_value
                        confidence_tracker[f'dimensions.{standard_name}'] = 75
                        source_tracker[f'dimensions.{standard_name}'] = common_psets[element_type]
        
        # Extract from ArchiCAD-specific quantities as fallback
        if 'ArchiCADQuantities' in psets:
            archicad_quantities = psets['ArchiCADQuantities']
            for standard_name, variants in dimension_mappings.items():
                if standard_name not in dimensions:
                    for variant in variants:
                        if variant in archicad_quantities:
                            dimensions[standard_name] = archicad_quantities[variant]
                            confidence_tracker[f'dimensions.{standard_name}'] = 60
                            source_tracker[f'dimensions.{standard_name}'] = 'ArchiCADQuantities'
                            break
        
        # Extract from ArchiCAD-specific element quantities
        for pset_name, properties in psets.items():
            if 'Equantity' in pset_name or 'Sachmerkmale' in pset_name:
                for standard_name, variants in dimension_mappings.items():
                    if standard_name not in dimensions:
                        for variant in variants:
                            if variant in properties:
                                dimensions[standard_name] = properties[variant]
                                confidence_tracker[f'dimensions.{standard_name}'] = 70
                                source_tracker[f'dimensions.{standard_name}'] = pset_name
                                break
        
        return dimensions
    
    def _extract_fire_rating(psets, confidence_tracker, source_tracker):
        """Extract fire rating information from property sets."""
        fire_rating = {}
        
        # Common fire rating property names (including German)
        fire_properties = ['FireRating', 'FireResistance', 'Brandklasse', 'FireClass', 'Brandschutzklasse', 'Feuerwiderstandsklasse']
        
        for pset_name, properties in psets.items():
            for fire_prop in fire_properties:
                if fire_prop in properties:
                    fire_rating['rating'] = properties[fire_prop]
                    confidence_tracker['fire_rating.rating'] = 80
                    source_tracker['fire_rating.rating'] = pset_name
                    return fire_rating
        
        return fire_rating
    
    def _extract_materials(element, model, confidence_tracker, source_tracker):
        """Extract material information from element associations."""
        materials = {}
        
        try:
            # Get material associations
            material_list = ifcopenshell.util.element.get_materials(element)
            
            if material_list:
                material_names = []
                material_layers = []
                
                for material in material_list:
                    if hasattr(material, 'Name') and material.Name:
                        material_names.append(material.Name)
                    
                    # Check for material layers (for compound elements)
                    if hasattr(material, 'ForMaterialLayerSet'):
                        layer_set = material.ForMaterialLayerSet
                        if hasattr(layer_set, 'MaterialLayers'):
                            for layer in layer_set.MaterialLayers:
                                if hasattr(layer, 'Material') and layer.Material.Name:
                                    material_layers.append({
                                        'name': layer.Material.Name,
                                        'thickness': getattr(layer, 'LayerThickness', None)
                                    })
                
                if material_names:
                    materials['names'] = material_names
                    confidence_tracker['materials.names'] = 95
                    source_tracker['materials.names'] = 'MaterialAssociation'
                
                if material_layers:
                    materials['layers'] = material_layers
                    confidence_tracker['materials.layers'] = 90
                    source_tracker['materials.layers'] = 'MaterialLayerSet'
        
        except Exception:
            pass  # Material extraction failed
        
        # Also try to extract materials from ArchiCAD properties
        psets = ifcopenshell.util.element.get_psets(element)
        for pset_name, properties in psets.items():
            if 'ArchiCADProperties' in pset_name:
                for prop_name, prop_value in properties.items():
                    if 'material' in prop_name.lower() or 'baustoff' in prop_name.lower() or 'oberfläche' in prop_name.lower():
                        if 'material_info' not in materials:
                            materials['material_info'] = {}
                        materials['material_info'][prop_name] = prop_value
                        confidence_tracker[f'materials.material_info.{prop_name}'] = 70
                        source_tracker[f'materials.material_info.{prop_name}'] = pset_name
        
        return materials
    
    def _extract_type_classification(element, psets, confidence_tracker, source_tracker):
        """Extract type-specific classification information."""
        classification = {}
        element_type = element.is_a()
        
        # Door-specific classifications
        if element_type == 'IfcDoor':
            # Look for operation type
            operation_props = ['OperationType', 'PanelOperation', 'Öffnungsart', 'IFC Betrieb (ifc_optypestr)']
            for pset_name, properties in psets.items():
                for prop in operation_props:
                    if prop in properties:
                        classification['operation_type'] = properties[prop]
                        confidence_tracker['type_classification.operation_type'] = 85
                        source_tracker['type_classification.operation_type'] = pset_name
                        break
        
        # Window-specific classifications
        elif element_type == 'IfcWindow':
            operation_props = ['OperationType', 'PanelOperation', 'Öffnungsart', 'IFC Betrieb (ifc_optypestr)']
            for pset_name, properties in psets.items():
                for prop in operation_props:
                    if prop in properties:
                        classification['operation_type'] = properties[prop]
                        confidence_tracker['type_classification.operation_type'] = 85
                        source_tracker['type_classification.operation_type'] = pset_name
                        break
        
        # Wall-specific classifications
        elif element_type in ['IfcWall', 'IfcWallStandardCase']:
            # Check for load bearing, external, etc.
            classification_props = ['LoadBearing', 'IsExternal', 'ExtendToStructure', 'Tragende Funktion', 'Lage']
            for pset_name, properties in psets.items():
                for prop in classification_props:
                    if prop in properties:
                        classification[prop.lower()] = properties[prop]
                        confidence_tracker[f'type_classification.{prop.lower()}'] = 80
                        source_tracker[f'type_classification.{prop.lower()}'] = pset_name
        
        # Structural element classifications
        elif element_type in ['IfcBeam', 'IfcColumn', 'IfcMember']:
            structural_props = ['LoadBearing', 'IsExternal', 'Reference', 'Tragende Funktion', 'Lage']
            for pset_name, properties in psets.items():
                for prop in structural_props:
                    if prop in properties:
                        classification[prop.lower()] = properties[prop]
                        confidence_tracker[f'type_classification.{prop.lower()}'] = 80
                        source_tracker[f'type_classification.{prop.lower()}'] = pset_name
        
        return classification
    
    def _standardize_dimension_name(property_name):
        """Standardize dimension property names to common conventions."""
        property_lower = property_name.lower()
        
        if any(word in property_lower for word in ['width', 'breite', 'paneelbreite', 'rahmen breite', 'durchgangslichte breite']):
            return 'width'
        elif any(word in property_lower for word in ['height', 'höhe', 'türblatt höhe', 'rahmen höhe', 'durchgangslichte höhe']):
            return 'height'
        elif any(word in property_lower for word in ['length', 'länge', 'wandlänge', 'länge der wand']):
            return 'length'
        elif any(word in property_lower for word in ['thickness', 'dicke', 'rahmen-dicke', 'türblatt stärke', 'wanddicke']):
            return 'thickness'
        elif any(word in property_lower for word in ['depth', 'tiefe', 'paneldepth', 'liningdepth', 'einfassung dicke']):
            return 'depth'
        else:
            return property_name.lower()
    
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
        
        # Find the element by GUID
        element = model.by_guid(element_guid)
        
        if not element:
            raise ValueError(f"Element with GUID {element_guid} not found")
        
        # Verify element type matches (or handle alternative representations)
        actual_type = element.is_a()
        
        # Handle IFC inheritance - check if actual type is a subtype of expected type
        type_match = False
        if actual_type == element_type:
            type_match = True
        elif element_type == 'IfcWall' and actual_type in ['IfcWallStandardCase', 'IfcWallElementedCase']:
            type_match = True
        elif element_type == 'IfcColumn' and actual_type in ['IfcMember', 'IfcBeam']:
            type_match = True
        elif element_type == 'IfcBeam' and actual_type == 'IfcMember':
            type_match = True
        elif element_type == 'IfcMember' and actual_type in ['IfcColumn', 'IfcBeam']:
            type_match = True
        
        if not type_match:
            raise ValueError(f"Element type mismatch: expected {element_type} or compatible types, got {actual_type}")
        
        # Basic element information
        result['element_info'] = {
            'name': element.Name or 'Unnamed',
            'guid': element.GlobalId,
            'type': actual_type,
            'description': getattr(element, 'Description', None)
        }
        
        # Get all property sets for the element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Also get property sets from the type definition if available
        type_psets = {}
        if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
            type_object = element.IsTypedBy[0].RelatingType
            type_psets = ifcopenshell.util.element.get_psets(type_object)
        
        # Merge element and type property sets
        all_psets = {**psets, **type_psets}
        
        # Initialize confidence tracking
        property_confidence = {}
        property_sources = {}
        
        # Extract dimensions based on element type
        dimensions = _extract_dimensions(element, all_psets, property_confidence, property_sources)
        result['dimensions'] = dimensions
        
        # Extract fire rating information
        fire_rating = _extract_fire_rating(all_psets, property_confidence, property_sources)
        result['fire_rating'] = fire_rating
        
        # Extract material information
        materials = _extract_materials(element, model, property_confidence, property_sources)
        result['materials'] = materials
        
        # Extract type-specific classification
        type_classification = _extract_type_classification(element, all_psets, property_confidence, property_sources)
        result['type_classification'] = type_classification
        
        # Calculate overall confidence level
        if property_confidence:
            result['confidence_level'] = sum(property_confidence.values()) / len(property_confidence)
        
        result['property_sources'] = property_sources
        
        # Filter by requested categories if specified
        if property_categories:
            filtered_result = {'element_info': result['element_info']}
            for category in property_categories:
                if category in result:
                    filtered_result[category] = result[category]
            filtered_result['confidence_level'] = result['confidence_level']
            filtered_result['property_sources'] = result['property_sources']
            result = filtered_result
        
    except Exception as e:
        result['error'] = str(e)
        result['confidence_level'] = 0
    
    return result