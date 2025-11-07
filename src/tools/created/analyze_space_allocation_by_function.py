import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any, Union
import logging

# Set up logging
logger = logging.getLogger(__name__)

def analyze_space_allocation_by_function(
    ifc_file,
    element_type: str = 'IfcSpace',
    category_property_set: Optional[str] = None,
    category_property_name: Optional[str] = None,
    area_property_names: List[str] = ['Berechnete Fläche (NRF)', 'Gemessene Fläche', 'Gemessene Nettofläche', 'GrossFloorArea', 'NetFloorArea'],
    name_property_names: List[str] = ['Raumname', 'LongName', 'Name'],
    include_individual_spaces: bool = True,
    sort_by_area: bool = True
) -> Dict[str, Any]:
    """
    Analyzes building space allocation by functional classification, extracting room categories, 
    areas, and calculating percentage distributions.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (default: 'IfcSpace')
        category_property_set: Property set containing functional category (default: None, auto-detects)
        category_property_name: Property name for functional category (default: None, auto-detects common names like 'Raumkategorie', 'Category')
        area_property_names: List of property names for area measurements (default: ['Berechnete Fläche (NRF)', 'Gemessene Fläche', 'Gemessene Nettofläche', 'GrossFloorArea', 'NetFloorArea'])
        name_property_names: List of property names for space names (default: ['Raumname', 'LongName', 'Name'])
        include_individual_spaces: Whether to include individual space details (default: True)
        sort_by_area: Whether to sort results by area (default: True)
    
    Returns:
        Dict containing:
        - total_area: Total building area
        - total_spaces: Total number of spaces
        - allocation_by_category: Dict with categories as keys and {total_area, percentage, count, spaces} as values
        - individual_spaces: List of individual space details (if include_individual_spaces=True)
        - summary: Overall allocation summary
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_space_allocation_by_function(model)
        >>> print(f"Total area: {result['total_area']:.2f} m²")
        >>> for category, data in result['allocation_by_category'].items():
        ...     print(f"{category}: {data['total_area']:.2f} m² ({data['percentage']:.1f}%)")
    """
    
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        if not elements:
            logger.warning(f"No elements of type '{element_type}' found in the model")
            return {
                'total_area': 0.0,
                'total_spaces': 0,
                'allocation_by_category': {},
                'individual_spaces': [],
                'summary': {'message': f'No {element_type} elements found'}
            }
        
        # Auto-detect category property names if not provided
        if category_property_name is None:
            category_property_name = 'Raumkategorie'  # Default to German
        
        space_data = []
        total_area = 0.0
        
        # Process each space
        for element in elements:
            space_info = {
                'global_id': getattr(element, 'GlobalId', ''),
                'name': getattr(element, 'Name', ''),
                'long_name': getattr(element, 'LongName', ''),
                'area': 0.0,
                'category': 'Unknown',
                'display_name': 'Unknown'
            }
            
            try:
                # Get all property sets and quantities
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Extract category information
                category_found = False
                for pset_name, pset_data in psets.items():
                    if isinstance(pset_data, dict):
                        # Look for category property
                        if category_property_name in pset_data:
                            space_info['category'] = str(pset_data[category_property_name])
                            category_found = True
                        
                        # Look for name properties
                        for name_prop in name_property_names:
                            if name_prop in pset_data:
                                space_info['display_name'] = str(pset_data[name_prop])
                                break
                        
                        # Look for area properties - use prioritized order
                        for area_prop in area_property_names:
                            if area_prop in pset_data:
                                try:
                                    area_value = float(pset_data[area_prop])
                                    # Use the first valid area found (prioritized by order in area_property_names)
                                    if space_info['area'] == 0.0:
                                        space_info['area'] = area_value
                                        break  # Stop after finding the first prioritized area
                                except (ValueError, TypeError):
                                    continue
                
                # If no category found, try to use element attributes
                if not category_found:
                    if hasattr(element, 'ObjectType') and element.ObjectType:
                        space_info['category'] = str(element.ObjectType)
                    elif space_info['long_name']:
                        space_info['category'] = space_info['long_name']
                
                # Use element name if no display name found
                if space_info['display_name'] == 'Unknown':
                    if space_info['long_name']:
                        space_info['display_name'] = space_info['long_name']
                    elif space_info['name']:
                        space_info['display_name'] = space_info['name']
                
                space_data.append(space_info)
                total_area += space_info['area']
                
            except Exception as e:
                logger.warning(f"Error processing element {getattr(element, 'GlobalId', 'Unknown')}: {e}")
                continue
        
        # Group by category and calculate statistics
        allocation_by_category = {}
        
        for space in space_data:
            category = space['category']
            if category not in allocation_by_category:
                allocation_by_category[category] = {
                    'total_area': 0.0,
                    'count': 0,
                    'spaces': []
                }
            
            allocation_by_category[category]['total_area'] += space['area']
            allocation_by_category[category]['count'] += 1
            allocation_by_category[category]['spaces'].append(space)
        
        # Calculate percentages and sort
        for category, data in allocation_by_category.items():
            data['percentage'] = (data['total_area'] / total_area * 100) if total_area > 0 else 0.0
            
            if sort_by_area:
                data['spaces'].sort(key=lambda x: x['area'], reverse=True)
        
        # Sort categories by total area
        if sort_by_area:
            allocation_by_category = dict(sorted(allocation_by_category.items(), 
                                                key=lambda x: x[1]['total_area'], reverse=True))
        
        # Sort individual spaces by area
        if sort_by_area:
            space_data.sort(key=lambda x: x['area'], reverse=True)
        
        # Create summary
        summary = {
            'total_elements': len(elements),
            'processed_elements': len(space_data),
            'total_categories': len(allocation_by_category),
            'largest_category': max(allocation_by_category.keys(), 
                                   key=lambda x: allocation_by_category[x]['total_area']) if allocation_by_category else None,
            'largest_space': max(space_data, key=lambda x: x['area']) if space_data else None
        }
        
        return {
            'total_area': total_area,
            'total_spaces': len(space_data),
            'allocation_by_category': allocation_by_category,
            'individual_spaces': space_data if include_individual_spaces else [],
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"Error in analyze_space_allocation_by_function: {e}")
        return {
            'total_area': 0.0,
            'total_spaces': 0,
            'allocation_by_category': {},
            'individual_spaces': [],
            'summary': {'error': str(e)}
        }