import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_cable_management_infrastructure(
    ifc_file,
    cable_element_types: List[str] = ['IfcCableCarrierSegment', 'IfcCableCarrierFitting', 'IfcDistributionChamberElement', 'IfcJunctionBox'],
    electrical_element_types: List[str] = ['IfcElectricDistributionBoard', 'IfcProtectiveDevice'],
    level_filter: Optional[List[str]] = None,
    include_property_details: bool = True,
    categorize_by_name: bool = True,
    calculate_totals: bool = True,
    max_elements_per_type: int = 100
) -> Dict[str, Any]:
    """
    Analyzes cable management infrastructure in IFC models by comprehensively examining cable carrier components and their integration with electrical systems.
    
    This function provides a complete breakdown of cable management components including segments, fittings, and distribution chambers,
    along with their specifications, quantities, and electrical system integration.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        cable_element_types: List of cable-related IFC element types to analyze
        electrical_element_types: List of electrical system elements to analyze integration
        level_filter: Optional list of building level names to filter analysis
        include_property_details: Whether to include detailed property analysis
        categorize_by_name: Whether to categorize components by their Name attribute
        calculate_totals: Whether to calculate total quantities and lengths
        max_elements_per_type: Maximum elements to analyze per type
    
    Returns:
        Dict containing:
        - summary: Total counts and overview
        - cable_components: Detailed breakdown by component type
        - fitting_categories: Categorization of fittings (bends, tees, etc.)
        - electrical_integration: Analysis of electrical system connections
        - specifications: Manufacturer and specification details
        - spatial_distribution: Component distribution by building level
        - calculated_totals: Total lengths, quantities, and infrastructure metrics
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_cable_management_infrastructure(model)
        >>> print(f"Total cable elements: {result['summary']['total_cable_elements']}")
        >>> print(f"Fitting types: {list(result['fitting_categories'].keys())}")
    """
    try:
        result = {
            'summary': {},
            'cable_components': {},
            'fitting_categories': {},
            'electrical_integration': {},
            'specifications': {},
            'spatial_distribution': {},
            'calculated_totals': {}
        }
        
        # Analyze cable components
        total_cable_elements = 0
        all_levels = set()
        specifications_data = {}
        
        for element_type in cable_element_types:
            elements = ifc_file.by_type(element_type)
            if max_elements_per_type and len(elements) > max_elements_per_type:
                elements = elements[:max_elements_per_type]
            
            element_data = []
            for element in elements:
                try:
                    # Get spatial container (building storey)
                    container = None
                    for rel in element.ContainedInStructure:
                        if hasattr(rel, 'RelatingStructure'):
                            container = rel.RelatingStructure
                            break
                    
                    level_name = container.Name if container and hasattr(container, 'Name') else 'Unknown'
                    all_levels.add(level_name)
                    
                    # Apply level filter if specified
                    if level_filter and level_name not in level_filter:
                        continue
                    
                    element_info = {
                        'id': element.id(),
                        'name': getattr(element, 'Name', None),
                        'object_type': getattr(element, 'ObjectType', None),
                        'description': getattr(element, 'Description', None),
                        'predefined_type': getattr(element, 'PredefinedType', None),
                        'container': {
                            'name': level_name,
                            'type': container.is_a() if container else None,
                            'id': container.id() if container else None
                        } if container else None
                    }
                    
                    # Get property sets if requested
                    if include_property_details:
                        try:
                            psets = ifcopenshell.util.element.get_psets(element)
                            element_info['property_sets'] = psets
                            
                            # Extract specification data
                            for pset_name, pset_data in psets.items():
                                if 'Manufacturer' in pset_data:
                                    if element_type not in specifications_data:
                                        specifications_data[element_type] = {}
                                    for key, value in pset_data.items():
                                        if key not in ['id']:
                                            specifications_data[element_type][key] = value
                        except:
                            element_info['property_sets'] = {}
                    
                    element_data.append(element_info)
                    total_cable_elements += 1
                    
                except Exception as e:
                    continue
            
            result['cable_components'][element_type] = {
                'count': len(element_data),
                'elements': element_data
            }
        
        # Store specifications data
        result['specifications'] = specifications_data
        
        # Categorize fittings by name if requested
        if categorize_by_name and 'IfcCableCarrierFitting' in result['cable_components']:
            fitting_elements = result['cable_components']['IfcCableCarrierFitting']['elements']
            categories = {}
            for element in fitting_elements:
                name = element.get('name', 'Unknown')
                if name not in categories:
                    categories[name] = {'count': 0, 'elements': []}
                categories[name]['count'] += 1
                categories[name]['elements'].append(element)
            result['fitting_categories'] = categories
        
        # Analyze electrical integration
        for element_type in electrical_element_types:
            elements = ifc_file.by_type(element_type)
            if max_elements_per_type and len(elements) > max_elements_per_type:
                elements = elements[:max_elements_per_type]
            
            element_data = []
            for element in elements:
                try:
                    # Get spatial container
                    container = None
                    for rel in element.ContainedInStructure:
                        if hasattr(rel, 'RelatingStructure'):
                            container = rel.RelatingStructure
                            break
                    
                    level_name = container.Name if container and hasattr(container, 'Name') else 'Unknown'
                    
                    element_info = {
                        'id': element.id(),
                        'name': getattr(element, 'Name', None),
                        'level': level_name
                    }
                    
                    if include_property_details:
                        try:
                            psets = ifcopenshell.util.element.get_psets(element)
                            element_info['property_sets'] = psets
                        except:
                            element_info['property_sets'] = {}
                    
                    element_data.append(element_info)
                except:
                    continue
            
            result['electrical_integration'][element_type] = {
                'count': len(element_data),
                'elements': element_data
            }
        
        # Calculate summary
        result['summary'] = {
            'total_cable_elements': total_cable_elements,
            'levels_found': list(all_levels),
            'cable_element_types_analyzed': cable_element_types
        }
        
        # Calculate spatial distribution
        result['spatial_distribution'] = {}
        for level in all_levels:
            level_count = 0
            for element_type, data in result['cable_components'].items():
                for element in data['elements']:
                    if element['container'] and element['container']['name'] == level:
                        level_count += 1
            result['spatial_distribution'][level] = level_count
        
        # Calculate totals if requested
        if calculate_totals:
            # Calculate total length for cable segments
            total_length = 0
            segment_count = 0
            if 'IfcCableCarrierSegment' in result['cable_components']:
                for element in result['cable_components']['IfcCableCarrierSegment']['elements']:
                    segment_count += 1
                    if 'property_sets' in element:
                        for pset_name, pset_data in element['property_sets'].items():
                            if 'NominalLength' in pset_data:
                                try:
                                    total_length += float(pset_data['NominalLength'])
                                except:
                                    pass
            
            # Calculate fitting totals
            fitting_count = 0
            if 'IfcCableCarrierFitting' in result['cable_components']:
                fitting_count = result['cable_components']['IfcCableCarrierFitting']['count']
            
            # Calculate chamber totals
            chamber_count = 0
            if 'IfcDistributionChamberElement' in result['cable_components']:
                chamber_count = result['cable_components']['IfcDistributionChamberElement']['count']
            
            result['calculated_totals'] = {
                'total_infrastructure_components': total_cable_elements,
                'total_cable_length': total_length,
                'cable_segments_count': segment_count,
                'cable_fittings_count': fitting_count,
                'distribution_chambers_count': chamber_count,
                'average_segment_length': total_length / segment_count if segment_count > 0 else 0
            }
        
        return result
        
    except Exception as e:
        return {'error': str(e)}