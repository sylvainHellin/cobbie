import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def search_building_energy_performance(
    ifc_file: ifcopenshell.file,
    rating_keywords: Optional[List[str]] = None,
    include_component_properties: bool = False,
    property_sets: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Searches for building-level energy performance ratings, certifications, and compliance information in an IFC model.
    
    This function specifically targets IfcBuilding elements and their property sets to find energy efficiency
    data like EPC ratings, energy certificates, performance classes, and compliance information. It uses
    semantic filtering with domain-specific keywords to identify energy-related properties that indicate
    building-level performance metrics rather than component-level technical specifications.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        rating_keywords: Optional list of keywords for energy ratings/certifications. Default includes
            common terms like 'rating', 'certificate', 'efficiency', 'class', 'epc', etc.
        include_component_properties: Boolean to also include component-level energy properties.
            Default: False (focuses on building-level data only)
        property_sets: Optional list of specific property sets to search. Default: searches all.
    
    Returns:
        Dict containing:
            - building_level_ratings: List of found building energy data with details
            - component_energy_properties: List of component energy properties (if requested)
            - search_summary: Summary of search process and results
            - analysis_notes: Notes about findings and limitations
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = search_building_energy_performance(model)
        >>> print(result['building_level_ratings'])
    """
    
    # Default keywords for energy ratings and certifications
    if rating_keywords is None:
        rating_keywords = [
            'rating', 'certificate', 'certification', 'performance', 'standard', 'class', 'label', 
            'epc', 'energypass', 'energieausweis', 'effizienzklasse', 'energieeffizienz', 
            'bedarfsausweis', 'verbrauchsausweis', 'energy', 'efficiency', 'consumption',
            'energie', 'effizienz', 'verbrauch', 'bewertung'
        ]
    
    # Initialize result structure
    result = {
        'building_level_ratings': [],
        'component_energy_properties': [],
        'search_summary': {
            'buildings_found': 0,
            'property_sets_checked': 0,
            'energy_properties_found': 0,
            'component_properties_found': 0
        },
        'analysis_notes': []
    }
    
    try:
        # Get all IfcBuilding elements
        buildings = ifc_file.by_type('IfcBuilding')
        result['search_summary']['buildings_found'] = len(buildings)
        
        if not buildings:
            result['analysis_notes'].append('No IfcBuilding elements found in model')
            return result
        
        # Search each building for energy-related properties
        for building in buildings:
            building_info = {
                'element_id': building.id(),
                'element_name': building.Name or 'Unnamed Building',
                'energy_properties': []
            }
            
            try:
                # Get all property sets for building
                psets = ifcopenshell.util.element.get_psets(building)
                
                # Filter property sets if specified
                if property_sets:
                    psets = {k: v for k, v in psets.items() if k in property_sets}
                
                result['search_summary']['property_sets_checked'] += len(psets)
                
                # Search for energy-related properties in each property set
                for pset_name, pset_data in psets.items():
                    if not isinstance(pset_data, dict):
                        continue
                        
                    for prop_name, prop_value in pset_data.items():
                        # Check if property name contains energy-related keywords
                        prop_name_lower = prop_name.lower()
                        if any(keyword.lower() in prop_name_lower for keyword in rating_keywords):
                            energy_prop = {
                                'property_set': pset_name,
                                'property_name': prop_name,
                                'property_value': prop_value,
                                'search_keyword_matched': [kw for kw in rating_keywords if kw.lower() in prop_name_lower]
                            }
                            building_info['energy_properties'].append(energy_prop)
                            result['search_summary']['energy_properties_found'] += 1
                
                result['building_level_ratings'].append(building_info)
                
            except Exception as e:
                result['analysis_notes'].append(f'Error processing building {building.Name}: {str(e)}')
                continue
        
        # Include component-level properties if requested
        if include_component_properties:
            component_keywords = ['energy', 'energie', 'efficiency', 'effizienz', 'consumption', 'verbrauch']
            
            # Search common component types that might have energy properties
            component_types = ['IfcWindow', 'IfcDoor', 'IfcWall', 'IfcSlab', 'IfcRoof']
            
            for comp_type in component_types:
                try:
                    components = ifc_file.by_type(comp_type)
                    for component in components:
                        comp_psets = ifcopenshell.util.element.get_psets(component)
                        
                        for pset_name, pset_data in comp_psets.items():
                            if not isinstance(pset_data, dict):
                                continue
                                
                            for prop_name, prop_value in pset_data.items():
                                prop_name_lower = prop_name.lower()
                                if any(keyword.lower() in prop_name_lower for keyword in component_keywords):
                                    comp_prop = {
                                        'element_id': component.id(),
                                        'element_name': component.Name or f'Unnamed {comp_type}',
                                        'element_type': comp_type,
                                        'property_set': pset_name,
                                        'property_name': prop_name,
                                        'property_value': prop_value
                                    }
                                    result['component_energy_properties'].append(comp_prop)
                                    result['search_summary']['component_properties_found'] += 1
                                    
                except Exception as e:
                    result['analysis_notes'].append(f'Error processing {comp_type} components: {str(e)}')
                    continue
        
        # Add analysis notes
        if result['search_summary']['energy_properties_found'] == 0:
            result['analysis_notes'].append('No building-level energy performance properties found')
        
        if include_component_properties and result['search_summary']['component_properties_found'] > 0:
            result['analysis_notes'].append(f'Found {result["search_summary"]["component_properties_found"]} component-level energy properties')
        
        return result
        
    except Exception as e:
        result['analysis_notes'].append(f'Critical error during search: {str(e)}')
        return result