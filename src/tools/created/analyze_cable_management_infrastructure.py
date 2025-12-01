import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_cable_management_infrastructure(
    ifc_file,
    cable_carrier_types: List[str] = ['IfcCableCarrierSegment', 'IfcCableCarrierFitting'],
    electrical_component_types: List[str] = ['IfcElectricDistributionBoard', 'IfcOutlet', 'IfcProtectiveDevice'],
    categorization_field: str = 'ObjectType',
    include_spatial_distribution: bool = True,
    include_electrical_integration: bool = True,
    max_examples_per_category: int = 5
) -> Dict[str, Any]:
    """
    Analyzes cable management infrastructure in IFC models including cable carriers, fittings, and integration with electrical systems.
    This function provides a comprehensive breakdown of cable management components, their quantities, spatial distribution,
    and electrical system integration. It handles the common BIM analysis pattern of discovering cable management elements,
    categorizing them by type, analyzing spatial distribution across building levels, and examining integration with
    electrical distribution systems.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        cable_carrier_types: List of cable carrier element types to analyze (default: ['IfcCableCarrierSegment', 'IfcCableCarrierFitting'])
        electrical_component_types: List of electrical component types for integration analysis (default: ['IfcElectricDistributionBoard', 'IfcOutlet', 'IfcProtectiveDevice'])
        categorization_field: Field to categorize elements by (default: 'ObjectType')
        include_spatial_distribution: Boolean to include analysis by building levels (default: True)
        include_electrical_integration: Boolean to include electrical system integration analysis (default: True)
        max_examples_per_category: Maximum examples to show per category (default: 5)
    
    Returns:
        Dict containing comprehensive cable management infrastructure analysis including component quantities,
        categorization, spatial distribution, and electrical system integration details.
        
    Example:
        >>> import ifcopenshell
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = analyze_cable_management_infrastructure(ifc_file)
        >>> print(f"Total cable carriers: {result['summary']['total_cable_carrier_components']}")
        >>> print(f"Spatial distribution: {result['spatial_distribution']['elements_by_storey']}")
    """
    try:
        result = {
            'cable_carrier_analysis': {},
            'electrical_integration': {},
            'spatial_distribution': {},
            'summary': {}
        }
        
        # Analyze cable carrier components
        for carrier_type in cable_carrier_types:
            elements = ifc_file.by_type(carrier_type)
            if elements:
                categories = {}
                for element in elements:
                    # Get categorization value
                    category_value = getattr(element, categorization_field, None)
                    if category_value is None:
                        category_value = 'null'
                    
                    if category_value not in categories:
                        categories[category_value] = {
                            'count': 0,
                            'examples': []
                        }
                    
                    categories[category_value]['count'] += 1
                    
                    if len(categories[category_value]['examples']) < max_examples_per_category:
                        categories[category_value]['examples'].append({
                            'id': element.id(),
                            'name': element.Name,
                            'global_id': element.GlobalId
                        })
                
                result['cable_carrier_analysis'][carrier_type] = {
                    'total_elements': len(elements),
                    'categories': categories
                }
        
        # Analyze electrical components if requested
        if include_electrical_integration:
            for elec_type in electrical_component_types:
                elements = ifc_file.by_type(elec_type)
                if elements:
                    categories = {}
                    for element in elements:
                        category_value = getattr(element, categorization_field, None)
                        if category_value is None:
                            category_value = 'null'
                        
                        if category_value not in categories:
                            categories[category_value] = {
                                'count': 0,
                                'examples': []
                            }
                        
                        categories[category_value]['count'] += 1
                        
                        if len(categories[category_value]['examples']) < max_examples_per_category:
                            categories[category_value]['examples'].append({
                                'id': element.id(),
                                'name': element.Name,
                                'global_id': element.GlobalId
                            })
                    
                    result['electrical_integration'][elec_type] = {
                        'total_elements': len(elements),
                        'categories': categories
                    }
        
        # Analyze spatial distribution if requested
        if include_spatial_distribution:
            spatial_analysis = {}
            all_types = cable_carrier_types + electrical_component_types
            
            # Get all building storeys
            storeys = ifc_file.by_type('IfcBuildingStorey')
            storey_info = []
            
            for storey in storeys:
                storey_name = getattr(storey, 'Name', 'Unknown')
                elevation = getattr(storey, 'Elevation', 0)
                storey_info.append({
                    'name': storey_name,
                    'id': storey.id(),
                    'elevation': elevation
                })
                
                # Get elements in this storey
                elements_in_storey = ifcopenshell.util.element.get_decomposition(storey)
                
                # Count elements by type
                type_counts = {}
                for element in elements_in_storey:
                    element_type = element.is_a()
                    if element_type in all_types:
                        if element_type not in type_counts:
                            type_counts[element_type] = 0
                        type_counts[element_type] += 1
                
                spatial_analysis[storey_name] = type_counts
            
            result['spatial_distribution'] = {
                'elements_by_storey': spatial_analysis,
                'storey_info': storey_info
            }
        
        # Create summary
        total_cable_carriers = sum(
            analysis['total_elements'] 
            for analysis in result['cable_carrier_analysis'].values()
        )
        
        total_electrical = sum(
            analysis['total_elements'] 
            for analysis in result['electrical_integration'].values()
        )
        
        result['summary'] = {
            'total_cable_carrier_components': total_cable_carriers,
            'total_electrical_components': total_electrical,
            'total_components': total_cable_carriers + total_electrical
        }
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'cable_carrier_analysis': {},
            'electrical_integration': {},
            'spatial_distribution': {},
            'summary': {}
        }