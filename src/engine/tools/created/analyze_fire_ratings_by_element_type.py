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


def analyze_fire_ratings_by_element_type(
    model_path: str, 
    element_type: str, 
    name_pattern: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyzes fire rating information for all elements of a specified type in an IFC model.
    
    This function iterates through all elements of the specified type, checks for fire rating
    properties using both standard IFC property sets and Revit-specific property sets, and returns
    a comprehensive summary grouped by element type/subtype.
    
    Args:
        model_path: Path to the IFC file
        element_type: IFC entity type (e.g., 'IfcDoor', 'IfcWall', 'IfcWindow', 'IfcSlab')
        name_pattern: Optional pattern to filter elements by name (supports wildcards)
    
    Returns:
        Dictionary containing:
        - total_elements: Total number of elements analyzed
        - elements_with_ratings: List of elements with fire ratings
        - elements_without_ratings: List of elements without fire ratings
        - breakdown_by_subtype: Dictionary grouping elements by subtype
        - confidence_summary: Summary of confidence levels based on property sources
    
    Note:
        This function handles both standard IFC property sets (e.g., Pset_FireProtectionRequirements)
        and Revit-specific property sets (e.g., PSet_Revit_FireRating) that may be present in
        models exported from Autodesk Revit.
    """
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all elements of the specified type
    elements = model.by_type(element_type)
    
    # Apply name pattern filter if provided
    if name_pattern:
        import fnmatch
        filtered_elements = []
        for element in elements:
            element_name = element.Name or ''
            if fnmatch.fnmatch(element_name.lower(), name_pattern.lower()):
                filtered_elements.append(element)
        elements = filtered_elements
    
    # Initialize results structure
    results = {
        'total_elements': len(elements),
        'elements_with_ratings': [],
        'elements_without_ratings': [],
        'breakdown_by_subtype': {},
        'confidence_summary': {
            'high_confidence': 0,  # Standard IFC property sets
            'medium_confidence': 0,  # Revit-specific property sets
            'low_confidence': 0,  # Non-standard or unclear sources
            'unknown': 0
        }
    }
    
    # Define common fire rating property names and their sources
    fire_rating_properties = {
        # Standard IFC property sets
        'Pset_FireProtectionRequirements': {
            'properties': ['FireRating', 'FireResistance', 'FireResistanceRating'],
            'confidence': 'high'
        },
        'Pset_WallCommon': {
            'properties': ['FireRating'],
            'confidence': 'high'
        },
        'Pset_DoorCommon': {
            'properties': ['FireRating'],
            'confidence': 'high'
        },
        'Pset_WindowCommon': {
            'properties': ['FireRating'],
            'confidence': 'high'
        },
        'Pset_SlabCommon': {
            'properties': ['FireRating'],
            'confidence': 'high'
        },
        # Revit-specific property sets
        'PSet_Revit_FireRating': {
            'properties': ['FireRating'],
            'confidence': 'medium'
        },
        'PSet_Revit_Dimensions': {
            'properties': ['FireRating'],
            'confidence': 'medium'
        },
        'PSet_Revit_Type': {
            'properties': ['FireRating'],
            'confidence': 'medium'
        }
    }
    
    # Helper function to extract subtype from element name
    def extract_subtype(element_name: str) -> str:
        """Extract subtype information from element name."""
        if not element_name:
            return 'Unknown'
        
        # Common patterns for subtype extraction
        name_lower = element_name.lower()
        
        # Look for common prefixes/suffixes that indicate subtypes
        if 'fire' in name_lower:
            return 'Fire-Rated'
        elif 'exterior' in name_lower or 'external' in name_lower:
            return 'Exterior'
        elif 'interior' in name_lower or 'internal' in name_lower:
            return 'Interior'
        elif 'load' in name_lower and 'bearing' in name_lower:
            return 'Load-Bearing'
        elif 'partition' in name_lower:
            return 'Partition'
        elif 'curtain' in name_lower:
            return 'Curtain Wall'
        else:
            return 'Standard'
    
    # Process each element
    for element in elements:
        element_name = element.Name or 'Unnamed'
        element_id = element.id()
        subtype = extract_subtype(element_name)
        
        # Initialize element result
        element_result = {
            'id': element_id,
            'name': element_name,
            'type': element_type,
            'subtype': subtype,
            'fire_rating': None,
            'rating_value': None,
            'source_property_set': None,
            'confidence': 'unknown'
        }
        
        # Get all property sets for the element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Search for fire rating properties
        found_rating = False
        
        for pset_name, properties in psets.items():
            # Check if this property set is in our known fire rating sources
            if pset_name in fire_rating_properties:
                pset_config = fire_rating_properties[pset_name]
                
                # Look for fire rating properties in this set
                for prop_name in pset_config['properties']:
                    if prop_name in properties:
                        element_result['fire_rating'] = prop_name
                        element_result['rating_value'] = properties[prop_name]
                        element_result['source_property_set'] = pset_name
                        element_result['confidence'] = pset_config['confidence']
                        found_rating = True
                        break
                
                if found_rating:
                    break
            
            # Also check for any property that might contain fire rating information
            # (case-insensitive search for fire-related terms)
            if not found_rating:
                for prop_name, prop_value in properties.items():
                    if any(term in prop_name.lower() for term in ['fire', 'rating', 'resistance']):
                        element_result['fire_rating'] = prop_name
                        element_result['rating_value'] = prop_value
                        element_result['source_property_set'] = pset_name
                        element_result['confidence'] = 'low'  # Non-standard source
                        found_rating = True
                        break
                
                if found_rating:
                    break
        
        # Update breakdown by subtype
        if subtype not in results['breakdown_by_subtype']:
            results['breakdown_by_subtype'][subtype] = {
                'total': 0,
                'with_ratings': 0,
                'without_ratings': 0
            }
        
        results['breakdown_by_subtype'][subtype]['total'] += 1
        
        # Categorize element based on whether fire rating was found
        if found_rating:
            results['elements_with_ratings'].append(element_result)
            results['breakdown_by_subtype'][subtype]['with_ratings'] += 1
            
            # Update confidence summary
            confidence = element_result['confidence']
            if confidence in results['confidence_summary']:
                results['confidence_summary'][confidence] += 1
            else:
                results['confidence_summary']['unknown'] += 1
        else:
            results['elements_without_ratings'].append(element_result)
            results['breakdown_by_subtype'][subtype]['without_ratings'] += 1
            results['confidence_summary']['unknown'] += 1
    
    # Add summary statistics
    results['elements_with_fire_ratings_count'] = len(results['elements_with_ratings'])
    results['elements_without_fire_ratings_count'] = len(results['elements_without_ratings'])
    results['fire_rating_coverage_percentage'] = (
        (results['elements_with_fire_ratings_count'] / results['total_elements'] * 100) 
        if results['total_elements'] > 0 else 0
    )
    
    return results