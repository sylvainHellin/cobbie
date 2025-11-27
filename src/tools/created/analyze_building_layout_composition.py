import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional, Union, Any, Tuple
import math

def analyze_building_layout_composition(
    ifc_file: ifcopenshell.file,
    building_filter_keywords: Optional[List[str]] = None,
    element_types_to_analyze: Optional[List[str]] = None,
    include_statistical_analysis: bool = True,
    include_layout_inference: bool = True,
    max_buildings_to_analyze: Optional[int] = None,
    include_detailed_examples: bool = True
) -> Dict[str, Any]:
    """
    Analyzes the interior layout and composition of buildings in an IFC model by examining spatial 
    containment relationships and element distributions. This function provides comprehensive insights 
    into building organization, element composition, and layout patterns by systematically analyzing 
    how elements are spatially organized within buildings.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        building_filter_keywords: Optional list of keywords to filter buildings by type 
            (e.g., ['haus', 'wohn'] for residential, ['office', 'commercial'] for commercial). 
            If None, analyzes all buildings.
        element_types_to_analyze: List of IFC element types to include in composition analysis 
            (default includes common building elements)
        include_statistical_analysis: Boolean to include statistical calculations (averages, ranges, distributions)
        include_layout_inference: Boolean to infer room counts and layout complexity from element patterns
        max_buildings_to_analyze: Optional limit on number of buildings to analyze (useful for large models)
        include_detailed_examples: Boolean to include detailed breakdowns of sample buildings
    
    Returns:
        Dict containing:
        - 'buildings_analyzed': Number of buildings processed
        - 'building_filter': Filter criteria used
        - 'composition_statistics': Element type distributions with averages and ranges
        - 'layout_patterns': Inferred layout characteristics (room counts, complexity)
        - 'detailed_examples': Sample building analyses (if requested)
        - 'summary': Key findings about building organization patterns
    
    Example usage:
        ```python
        import ifcopenshell
        
        # Load IFC model
        model = ifcopenshell.open('building_model.ifc')
        
        # Analyze residential building layouts
        results = analyze_building_layout_composition(
            ifc_file=model,
            building_filter_keywords=['haus', 'wohn'],
            include_statistical_analysis=True,
            include_layout_inference=True
        )
        
        print(f"Analyzed {results['buildings_analyzed']} buildings")
        print(f"Average walls per building: {results['composition_statistics']['element_types']['IfcWallStandardCase']['average']:.1f}")
        ```
    """
    
    # Default element types to analyze if not specified
    if element_types_to_analyze is None:
        element_types_to_analyze = [
            'IfcWall', 'IfcWallStandardCase', 'IfcDoor', 'IfcWindow', 
            'IfcSlab', 'IfcRoof', 'IfcColumn', 'IfcBeam', 'IfcStair',
            'IfcSpace', 'IfcRoom', 'IfcBuildingStorey'
        ]
    
    try:
        # Get all buildings in the model
        all_buildings = ifc_file.by_type('IfcBuilding')
        
        # Filter buildings by keywords if specified
        if building_filter_keywords:
            filtered_buildings = []
            for building in all_buildings:
                building_name = building.Name if building.Name else ""
                if any(keyword.lower() in building_name.lower() for keyword in building_filter_keywords):
                    filtered_buildings.append(building)
            buildings_to_analyze = filtered_buildings
        else:
            buildings_to_analyze = list(all_buildings)
        
        # Apply max buildings limit if specified
        if max_buildings_to_analyze and len(buildings_to_analyze) > max_buildings_to_analyze:
            buildings_to_analyze = buildings_to_analyze[:max_buildings_to_analyze]
        
        # Initialize result structure
        result = {
            'buildings_analyzed': len(buildings_to_analyze),
            'building_filter': building_filter_keywords,
            'composition_statistics': {},
            'layout_patterns': {},
            'detailed_examples': {},
            'summary': {}
        }
        
        # Get spatial containment relationships
        spatial_containers = ifc_file.by_type('IfcRelContainedInSpatialStructure')
        
        # Build composition data for each building
        building_compositions = {}
        element_type_counts = {elem_type: [] for elem_type in element_types_to_analyze}
        building_sizes = []
        
        # Create a set of building IDs for faster lookup
        building_ids = {building.id() for building in buildings_to_analyze}
        
        for rel in spatial_containers:
            if (hasattr(rel, 'RelatingStructure') and 
                rel.RelatingStructure.id() in building_ids):
                
                building = rel.RelatingStructure
                building_name = building.Name if building.Name else "Unnamed"
                
                if building_name not in building_compositions:
                    building_compositions[building_name] = {
                        'building': building,
                        'elements': {},
                        'total_elements': 0
                    }
                
                if hasattr(rel, 'RelatedElements'):
                    for elem in rel.RelatedElements:
                        elem_type = elem.is_a()
                        if elem_type in element_types_to_analyze:
                            building_compositions[building_name]['elements'][elem_type] = \
                                building_compositions[building_name]['elements'].get(elem_type, 0) + 1
                            building_compositions[building_name]['total_elements'] += 1
        
        # Collect statistics
        for name, composition in building_compositions.items():
            elements = composition['elements']
            total = composition['total_elements']
            building_sizes.append(total)
            
            for elem_type in element_types_to_analyze:
                count = elements.get(elem_type, 0)
                element_type_counts[elem_type].append(count)
        
        # Generate composition statistics
        if include_statistical_analysis:
            result['composition_statistics'] = {
                'building_size_distribution': {
                    'average': sum(building_sizes) / len(building_sizes) if building_sizes else 0,
                    'min': min(building_sizes) if building_sizes else 0,
                    'max': max(building_sizes) if building_sizes else 0,
                    'count': len(building_sizes)
                },
                'element_types': {}
            }
            
            for elem_type, counts in element_type_counts.items():
                if counts:  # Only include if we have data
                    non_zero_counts = [c for c in counts if c > 0]
                    result['composition_statistics']['element_types'][elem_type] = {
                        'average': sum(counts) / len(counts),
                        'min': min(counts),
                        'max': max(counts),
                        'buildings_with_element': len(non_zero_counts),
                        'total_buildings': len(counts),
                        'percentage': (len(non_zero_counts) / len(counts) * 100) if counts else 0
                    }
        
        # Generate layout patterns
        if include_layout_inference:
            layout_patterns = {
                'room_estimates': [],
                'complexity_distribution': {'simple': 0, 'moderate': 0, 'complex': 0},
                'spatial_organization': {}
            }
            
            for name, composition in building_compositions.items():
                elements = composition['elements']
                walls = elements.get('IfcWallStandardCase', 0) + elements.get('IfcWall', 0)
                doors = elements.get('IfcDoor', 0)
                spaces = elements.get('IfcSpace', 0) + elements.get('IfcRoom', 0)
                storeys = elements.get('IfcBuildingStorey', 0)
                
                # Estimate room count
                if spaces > 0:
                    estimated_rooms = spaces
                elif walls > 0 and doors > 0:
                    estimated_rooms = min(doors, max(1, walls // 4))
                else:
                    estimated_rooms = 1
                
                layout_patterns['room_estimates'].append(estimated_rooms)
                
                # Determine complexity
                if walls > 8 or storeys > 1:
                    complexity = 'complex'
                elif walls > 4:
                    complexity = 'moderate'
                else:
                    complexity = 'simple'
                
                layout_patterns['complexity_distribution'][complexity] += 1
            
            # Calculate averages for layout patterns
            if layout_patterns['room_estimates']:
                layout_patterns['average_rooms'] = sum(layout_patterns['room_estimates']) / len(layout_patterns['room_estimates'])
                layout_patterns['room_range'] = [min(layout_patterns['room_estimates']), max(layout_patterns['room_estimates'])]
            
            result['layout_patterns'] = layout_patterns
        
        # Generate detailed examples
        if include_detailed_examples and building_compositions:
            sample_buildings = list(building_compositions.items())[:3]  # First 3 buildings
            
            for i, (name, composition) in enumerate(sample_buildings):
                elements = composition['elements']
                
                example = {
                    'building_name': name,
                    'total_elements': composition['total_elements'],
                    'element_breakdown': elements,
                    'layout_inference': {}
                }
                
                # Add layout inference for this example
                walls = elements.get('IfcWallStandardCase', 0) + elements.get('IfcWall', 0)
                doors = elements.get('IfcDoor', 0)
                windows = elements.get('IfcWindow', 0)
                
                if walls > 0 and doors > 0:
                    estimated_rooms = min(doors, max(1, walls // 4))
                    example['layout_inference']['estimated_rooms'] = estimated_rooms
                    
                    if walls > 8:
                        complexity = "Complex (multi-room)"
                    elif walls > 4:
                        complexity = "Moderate (2-3 rooms)"
                    else:
                        complexity = "Simple (1-2 rooms)"
                    example['layout_inference']['complexity'] = complexity
                
                result['detailed_examples'][f'example_{i+1}'] = example
        
        # Generate summary
        has_explicit_spaces = False
        if include_statistical_analysis and 'element_types' in result['composition_statistics']:
            has_explicit_spaces = (
                result['composition_statistics']['element_types'].get('IfcSpace', {}).get('buildings_with_element', 0) > 0 or
                result['composition_statistics']['element_types'].get('IfcRoom', {}).get('buildings_with_element', 0) > 0
            )
        
        result['summary'] = {
            'total_buildings_found': len(all_buildings),
            'buildings_analyzed': len(buildings_to_analyze),
            'filter_applied': building_filter_keywords is not None,
            'has_explicit_spaces': has_explicit_spaces,
            'modeling_approach': 'explicit_spaces' if has_explicit_spaces else 'implied_layout'
        }
        
        return result
        
    except Exception as e:
        return {
            'error': f"Error analyzing building layout composition: {str(e)}",
            'buildings_analyzed': 0,
            'building_filter': building_filter_keywords,
            'composition_statistics': {},
            'layout_patterns': {},
            'detailed_examples': {},
            'summary': {}
        }