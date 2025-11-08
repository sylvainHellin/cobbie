import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Union, Any

def calculate_total_quantity_by_property_categories(
    ifc_file,
    element_type: str,
    category_property_set: str,
    category_property_name: str,
    quantity_property_set: str,
    quantity_property_name: str,
    include_breakdown: bool = True
) -> Dict[str, Any]:
    """
    Calculates total quantities of IFC elements categorized by their property values.
    
    This function handles the common pattern of categorizing elements by properties 
    (like IsExternal, LoadBearing, FireRating) and then summing associated quantities 
    (like Length, Area, Volume) stored in property sets. It's particularly useful when 
    quantity data is stored in property sets rather than standard quantity sets, which 
    is common in many BIM models.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcWall', 'IfcDoor', 'IfcColumn')
        category_property_set: Property set containing categorization property 
            (e.g., 'Pset_WallCommon', 'Pset_DoorCommon')
        category_property_name: Property name for categorization 
            (e.g., 'IsExternal', 'LoadBearing', 'FireRating')
        quantity_property_set: Property set containing quantity 
            (e.g., 'Abmessungen', 'Qto_WallBaseQuantities')
        quantity_property_name: Property name for quantity 
            (e.g., 'Länge', 'Area', 'Volume')
        include_breakdown: Whether to return category breakdown (default: True)
    
    Returns:
        Dict with total quantities, category breakdowns, and processing statistics:
        {
            'total_quantity': float,  # Total quantity across all categories
            'processed_elements': int,  # Number of elements successfully processed
            'skipped_elements': int,  # Number of elements skipped due to missing data
            'total_elements': int,  # Total number of elements found
            'category_breakdown': {  # Optional (only if include_breakdown=True)
                'category_value': {
                    'quantity': float,  # Total quantity for this category
                    'count': int  # Number of elements in this category
                }
            }
        }
    
    Example usage:
        # Calculate total length of exterior vs interior walls
        result = calculate_total_quantity_by_property_categories(
            ifc_file=ifc_file,
            element_type='IfcWall',
            category_property_set='Pset_WallCommon',
            category_property_name='IsExternal',
            quantity_property_set='Abmessungen',
            quantity_property_name='Länge'
        )
        
        # Calculate total area of fire-rated vs non-fire-rated doors
        result = calculate_total_quantity_by_property_categories(
            ifc_file=ifc_file,
            element_type='IfcDoor',
            category_property_set='Pset_DoorCommon',
            category_property_name='FireRating',
            quantity_property_set='Qto_DoorBaseQuantities',
            quantity_property_name='Area'
        )
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Initialize results
        category_totals = {}
        total_quantity = 0
        processed_count = 0
        skipped_count = 0
        
        # Process each element
        for element in elements:
            try:
                # Get category value
                category_value = ifcopenshell.util.element.get_pset(
                    element, category_property_set, category_property_name
                )
                
                # Get quantity value
                quantity_value = ifcopenshell.util.element.get_pset(
                    element, quantity_property_set, quantity_property_name
                )
                
                # Skip if either value is missing
                if category_value is None or quantity_value is None:
                    skipped_count += 1
                    continue
                
                # Convert category to string for dictionary key
                category_key = str(category_value)
                
                # Initialize category if not exists
                if category_key not in category_totals:
                    category_totals[category_key] = {
                        'quantity': 0,
                        'count': 0
                    }
                
                # Add to totals
                category_totals[category_key]['quantity'] += float(quantity_value)
                category_totals[category_key]['count'] += 1
                total_quantity += float(quantity_value)
                processed_count += 1
                
            except Exception as e:
                skipped_count += 1
                continue
        
        # Prepare result
        result = {
            'total_quantity': total_quantity,
            'processed_elements': processed_count,
            'skipped_elements': skipped_count,
            'total_elements': len(elements)
        }
        
        if include_breakdown:
            result['category_breakdown'] = category_totals
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'total_quantity': 0,
            'processed_elements': 0,
            'skipped_elements': 0,
            'total_elements': 0
        }