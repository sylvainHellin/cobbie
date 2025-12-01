import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Union, Any
import re


def analyze_building_type_and_function(
    ifc_file: ifcopenshell.file,
    building_index: int = 0,
    include_structural_analysis: bool = True,
    include_spatial_analysis: bool = True,
    semantic_keywords: Optional[Dict[str, List[str]]] = None,
    confidence_threshold: float = 0.6,
    include_detailed_evidence: bool = True
) -> Dict[str, Any]:
    """
    Analyzes an IFC building to determine its type and primary function through multi-source data synthesis.
    
    This function implements a comprehensive building characterization workflow:
    1) Extracts building metadata (name, description, properties)
    2) Analyzes structural composition (storeys, elevations)
    3) Examines spatial organization (space count, distribution)
    4) Applies semantic analysis to infer building type/function from naming patterns
    5) Provides confidence indicators and supporting evidence
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        building_index: Index of building to analyze if multiple exist (default: 0)
        include_structural_analysis: Boolean to include storey/floor analysis (default: True)
        include_spatial_analysis: Boolean to include space analysis (default: True)
        semantic_keywords: Dict mapping building types to keyword lists for name analysis
                           (default: includes common terms like 'office', 'residential', 'retail', etc.)
        confidence_threshold: Minimum confidence score for type inference (default: 0.6)
        include_detailed_evidence: Boolean to include detailed evidence for conclusions (default: True)
    
    Returns:
        Dict containing:
        - building_type: Inferred building type (e.g., 'office', 'residential', 'mixed_use')
        - building_function: Primary function description
        - confidence_score: Confidence level (0-1)
        - supporting_evidence: List of evidence points
        - structural_summary: Building structure details
        - spatial_summary: Space and area details
        - multilingual_indicators: Detected language patterns
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_building_type_and_function(model)
        >>> print(f"Building Type: {result['building_type']}")
        >>> print(f"Confidence: {result['confidence_score']:.2f}")
    """
    
    # Enhanced semantic keywords for building type detection
    default_keywords = {
        'office': [
            # English terms
            'office', 'business', 'commercial', 'work', 'corporate', 'administration',
            # German terms
            'büro', 'buro', 'buerogebaeude', 'bürogebäude', 'geschäft', 'gewerbe',
            'verwaltung', 'arbeitsplatz', 'firmen', 'unternehmens',
            # Compound variations
            'office building', 'officebuilding', 'buro building', 'buerogebaeude'
        ],
        'residential': [
            # English terms
            'residential', 'apartment', 'home', 'house', 'dwelling', 'housing',
            # German terms
            'wohnung', 'wohnheim', 'haus', 'wohnen', 'wohngebäude', 'residenz'
        ],
        'retail': [
            # English terms
            'retail', 'shop', 'store', 'mall', 'shopping', 'sales',
            # German terms
            'geschäft', 'laden', 'einkauf', 'handel', 'verkauf', 'kaufhaus'
        ],
        'industrial': [
            # English terms
            'industrial', 'factory', 'warehouse', 'production', 'manufacturing',
            # German terms
            'fabrik', 'werk', 'produktion', 'lager', 'industrie', 'fertigung'
        ],
        'educational': [
            # English terms
            'school', 'university', 'education', 'college', 'academic',
            # German terms
            'schule', 'universität', 'bildung', 'akademie', 'lehranstalt'
        ],
        'healthcare': [
            # English terms
            'hospital', 'clinic', 'medical', 'healthcare', 'health',
            # German terms
            'krankenhaus', 'klinik', 'medizin', 'gesundheit', 'arzt'
        ],
        'mixed_use': [
            'mixed', 'combined', 'multi', 'hybrid', 'gemischt', 'kombiniert'
        ]
    }
    
    if semantic_keywords is None:
        semantic_keywords = default_keywords
    
    try:
        # Initialize result structure
        result = {
            'building_type': 'unknown',
            'building_function': 'Unknown function',
            'confidence_score': 0.0,
            'supporting_evidence': [],
            'structural_summary': {},
            'spatial_summary': {},
            'multilingual_indicators': {}
        }
        
        # Get buildings
        buildings = ifc_file.by_type('IfcBuilding')
        if not buildings:
            result['supporting_evidence'].append('No IfcBuilding elements found in model')
            return result
        
        if building_index >= len(buildings):
            result['supporting_evidence'].append(f'Building index {building_index} out of range (found {len(buildings)} buildings)')
            return result
        
        building = buildings[building_index]
        
        # Extract basic building metadata
        building_name = getattr(building, 'Name', None) or 'Unnamed Building'
        building_description = getattr(building, 'Description', None) or 'No description'
        building_object_type = getattr(building, 'ObjectType', None)
        building_long_name = getattr(building, 'LongName', None)
        
        # Store metadata
        result['structural_summary']['building_name'] = building_name
        result['structural_summary']['building_description'] = building_description
        result['structural_summary']['object_type'] = building_object_type
        result['structural_summary']['long_name'] = building_long_name
        
        # Also check project name for additional context
        projects = ifc_file.by_type('IfcProject')
        if projects:
            project_name = getattr(projects[0], 'Name', None)
            if project_name:
                result['structural_summary']['project_name'] = project_name
        
        # Analyze building properties
        properties = {}
        for definition in building.IsDefinedBy:
            if hasattr(definition, 'RelatingPropertyDefinition'):
                prop_def = definition.RelatingPropertyDefinition
                if hasattr(prop_def, 'Name') and hasattr(prop_def, 'HasProperties'):
                    pset_name = prop_def.Name
                    pset_props = {}
                    for prop in prop_def.HasProperties:
                        if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                            pset_props[prop.Name] = prop.NominalValue.wrappedValue
                    properties[pset_name] = pset_props
        
        result['structural_summary']['properties'] = properties
        
        # Structural analysis - storeys
        if include_structural_analysis:
            storeys = ifc_file.by_type('IfcBuildingStorey')
            storey_info = []
            german_storey_count = 0
            english_storey_count = 0
            
            for storey in storeys:
                storey_name = getattr(storey, 'Name', 'Unnamed Storey')
                elevation = getattr(storey, 'Elevation', None)
                
                # Count language indicators in storey names
                storey_name_lower = storey_name.lower()
                if any(term in storey_name_lower for term in ['keller', 'erdgeschoss', 'obergeschoss', 'dachgeschoss']):
                    german_storey_count += 1
                elif any(term in storey_name_lower for term in ['basement', 'ground', 'floor', 'level']):
                    english_storey_count += 1
                
                storey_info.append({
                    'name': storey_name,
                    'elevation': elevation
                })
            
            # Sort by elevation if available
            storey_info.sort(key=lambda x: x['elevation'] if x['elevation'] is not None else float('-inf'))
            
            result['structural_summary']['storeys'] = storey_info
            result['structural_summary']['total_storeys'] = len(storeys)
            
            # Add evidence about building structure
            if len(storeys) > 0:
                result['supporting_evidence'].append(f'Building has {len(storeys)} storeys')
                if len(storeys) >= 5:
                    result['supporting_evidence'].append('Multi-storey building suggests commercial/office use')
        
        # Spatial analysis - spaces
        if include_spatial_analysis:
            spaces = ifc_file.by_type('IfcSpace')
            space_info = {
                'total_spaces': len(spaces),
                'space_types': {},
                'space_names': []
            }
            
            for space in spaces[:20]:  # Analyze first 20 spaces for patterns
                space_name = getattr(space, 'Name', 'Unnamed Space')
                space_obj_type = getattr(space, 'ObjectType', None)
                space_info['space_names'].append(space_name)
                
                # Categorize spaces
                if space_obj_type:
                    space_info['space_types'][space_obj_type] = space_info['space_types'].get(space_obj_type, 0) + 1
            
            result['spatial_summary'] = space_info
            
            # Add evidence about spatial organization
            if len(spaces) > 0:
                result['supporting_evidence'].append(f'Building contains {len(spaces)} spaces')
                if len(spaces) > 50:
                    result['supporting_evidence'].append('High space count suggests commercial/office building')
        
        # Enhanced semantic analysis of building names
        all_text_sources = [building_name, building_description, building_object_type, building_long_name]
        if 'project_name' in result['structural_summary']:
            all_text_sources.append(result['structural_summary']['project_name'])
        
        all_text = ' '.join([str(text) for text in all_text_sources if text]).lower()
        
        # Enhanced multilingual detection
        german_indicators = ['buerogebaeude', 'büro', 'geschoss', 'keller', 'erdgeschoss', 'obergeschoss', 'dachgeschoss', 'gebäude', 'gebaeude']
        english_indicators = ['office', 'building', 'floor', 'ground', 'basement', 'level', 'story', 'storey']
        
        german_count = sum(1 for indicator in german_indicators if indicator in all_text)
        english_count = sum(1 for indicator in english_indicators if indicator in all_text)
        
        # Also consider storey name language indicators
        if include_structural_analysis and 'storeys' in result['structural_summary']:
            german_count += german_storey_count
            english_count += english_storey_count
        
        if german_count > english_count and german_count > 0:
            result['multilingual_indicators']['primary_language'] = 'german'
            result['multilingual_indicators']['confidence'] = min(german_count / (german_count + english_count), 1.0)
            result['supporting_evidence'].append(f'Detected German language indicators (count: {german_count})')
        elif english_count > 0:
            result['multilingual_indicators']['primary_language'] = 'english'
            result['multilingual_indicators']['confidence'] = min(english_count / (german_count + english_count), 1.0)
            result['supporting_evidence'].append(f'Detected English language indicators (count: {english_count})')
        
        # Enhanced building type inference
        type_scores = {}
        for building_type, keywords in semantic_keywords.items():
            score = 0
            matched_keywords = []
            for keyword in keywords:
                if keyword.lower() in all_text:
                    score += 1
                    matched_keywords.append(keyword)
            
            if score > 0:
                # Calculate confidence based on keyword matches and keyword list size
                confidence = score / len(keywords)
                # Boost confidence for exact matches or compound terms
                if any(len(keyword.split()) > 1 for keyword in matched_keywords):
                    confidence += 0.2
                
                type_scores[building_type] = {
                    'score': score,
                    'matched_keywords': matched_keywords,
                    'confidence': min(confidence, 1.0)
                }
        
        # Determine building type with highest confidence
        if type_scores:
            best_type = max(type_scores.items(), key=lambda x: x[1]['confidence'])
            building_type = best_type[0]
            confidence = best_type[1]['confidence']
            
            if confidence >= confidence_threshold:
                result['building_type'] = building_type
                result['confidence_score'] = confidence
                result['supporting_evidence'].append(f"Semantic analysis detected '{building_type}' with confidence {confidence:.2f}")
                result['supporting_evidence'].append(f"Matched keywords: {', '.join(best_type[1]['matched_keywords'])}")
                
                # Generate function description
                function_descriptions = {
                    'office': 'Commercial office building for business operations',
                    'residential': 'Residential building for housing',
                    'retail': 'Commercial retail building for shopping and sales',
                    'industrial': 'Industrial building for manufacturing or warehousing',
                    'educational': 'Educational facility for learning and instruction',
                    'healthcare': 'Healthcare facility for medical services',
                    'mixed_use': 'Mixed-use building with multiple functions',
                    'commercial': 'Commercial building for business activities'
                }
                result['building_function'] = function_descriptions.get(building_type, f'{building_type.title()} building')
            else:
                result['supporting_evidence'].append(f'Semantic analysis detected potential types but confidence below threshold ({confidence_threshold})')
        
        # Add area information if available
        if 'BaseQuantities' in properties:
            base_quantities = properties['BaseQuantities']
            if 'GrossFloorArea' in base_quantities:
                area = base_quantities['GrossFloorArea']
                result['spatial_summary']['gross_floor_area'] = area
                result['supporting_evidence'].append(f'Gross floor area: {area:.2f} m²')
                
                # Use area as additional evidence
                if area > 2000:
                    result['supporting_evidence'].append('Large floor area suggests commercial building')
        
        # Enhanced heuristics if still unknown
        if result['building_type'] == 'unknown':
            # Check for German office building patterns
            if 'buerogebaeude' in all_text or 'bürogebäude' in all_text:
                result['building_type'] = 'office'
                result['building_function'] = 'German office building (Bürogebäude)'
                result['confidence_score'] = 0.8
                result['supporting_evidence'].append('Detected German office building terminology')
            elif len(spaces) > 30 and len(storeys) > 3:
                result['building_type'] = 'commercial'
                result['building_function'] = 'Commercial building (inferred from size and complexity)'
                result['confidence_score'] = 0.4
                result['supporting_evidence'].append('Inferred commercial type from spatial complexity')
            elif len(spaces) > 0:
                result['building_type'] = 'general'
                result['building_function'] = 'General purpose building'
                result['confidence_score'] = 0.3
                result['supporting_evidence'].append('Limited information available for type determination')
        
        return result
        
    except Exception as e:
        return {
            'building_type': 'error',
            'building_function': f'Analysis failed: {str(e)}',
            'confidence_score': 0.0,
            'supporting_evidence': [f'Error during analysis: {str(e)}'],
            'structural_summary': {},
            'spatial_summary': {},
            'multilingual_indicators': {}
        }