#!/usr/bin/env python3
"""
Script to extract all building element types and sub-types from an IFC file.
This script analyzes the IFC model and provides a comprehensive overview of all element types,
their predefined types, and classifications found in the model.
"""

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.classification
import ifcopenshell.util.selector
from typing import Dict, List, Set, Optional
from collections import defaultdict
import sys


def analyze_ifc_elements(model_path: str) -> Dict:
    """
    Analyze an IFC model to extract all element types and sub-types.

    Args:
        model_path (str): Path to the IFC model file

    Returns:
        Dict: Comprehensive analysis of element types and sub-types
    """
    try:
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise Exception(f"Failed to load IFC model from {model_path}: {str(e)}")

    analysis = {
        'model_info': {
            'file_path': model_path,
            'schema': model.schema,
            'total_elements': 0,
            'total_entities': 0
        },
        'element_types': defaultdict(lambda: {
            'count': 0,
            'predefined_types': set(),
            'classifications': set(),
            'type_objects': set(),
            'sample_elements': []
        }),
        'type_objects': defaultdict(lambda: {
            'count': 0,
            'predefined_types': set(),
            'occurrences': set()
        }),
        'classification_systems': set(),
        'summary': {}
    }

    # Get ALL entities in the model (for reference)
    all_entities = []
    for ifc_class in model.types():
        entities = model.by_type(ifc_class)
        all_entities.extend(entities)

    analysis['model_info']['total_entities'] = len(all_entities)

    # Filter to only building elements (not geometric primitives)
    building_elements = []
    for entity in all_entities:
        ifc_class = entity.is_a()
        if is_concrete_element_type(ifc_class):
            building_elements.append(entity)

    analysis['model_info']['total_elements'] = len(building_elements)

    # Analyze each building element
    for element in building_elements:
        ifc_class = element.is_a()

        element_info = analysis['element_types'][ifc_class]
        element_info['count'] += 1

        # Store sample elements (first 3 of each type)
        if len(element_info['sample_elements']) < 3:
            element_info['sample_elements'].append({
                'id': element.id(),
                'name': getattr(element, 'Name', None),
                'guid': getattr(element, 'GlobalId', None)
            })

        # Get predefined type
        if hasattr(element, 'PredefinedType') and element.PredefinedType:
            element_info['predefined_types'].add(element.PredefinedType)

        # Get type information (for element occurrences)
        try:
            type_obj = ifcopenshell.util.element.get_type(element)
            if type_obj:
                element_info['type_objects'].add(type_obj.is_a())

                # Analyze the type object
                type_info = analysis['type_objects'][type_obj.is_a()]
                type_info['count'] += 1
                type_info['occurrences'].add(element.id())

                if hasattr(type_obj, 'PredefinedType') and type_obj.PredefinedType:
                    type_info['predefined_types'].add(type_obj.PredefinedType)
        except Exception:
            pass  # Some elements might not have types

        # Get classifications
        try:
            references = ifcopenshell.util.classification.get_references(element)
            for ref in references:
                if hasattr(ref, 'Name') and ref.Name:
                    element_info['classifications'].add(f"{ref.Name}")

                # Get classification system
                try:
                    system = ifcopenshell.util.classification.get_classification(ref)
                    if system and hasattr(system, 'Name'):
                        analysis['classification_systems'].add(system.Name)
                except Exception:
                    pass
        except Exception:
            pass  # Some elements might not have classifications

    # Convert sets to sorted lists for better readability
    for ifc_class, info in analysis['element_types'].items():
        info['predefined_types'] = sorted(list(info['predefined_types']))
        info['classifications'] = sorted(list(info['classifications']))
        info['type_objects'] = sorted(list(info['type_objects']))

    for type_class, info in analysis['type_objects'].items():
        info['predefined_types'] = sorted(list(info['predefined_types']))
        info['occurrences'] = sorted(list(info['occurrences']))

    analysis['classification_systems'] = sorted(list(analysis['classification_systems']))

    # Generate summary
    analysis['summary'] = {
        'total_element_types': len(analysis['element_types']),
        'total_type_objects': len(analysis['type_objects']),
        'total_classification_systems': len(analysis['classification_systems']),
        'most_common_elements': sorted(
            [(ifc_class, info['count']) for ifc_class, info in analysis['element_types'].items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
    }

    return analysis


def is_concrete_element_type(ifc_class: str) -> bool:
    """
    Determine if an IFC class represents a concrete building element type.
    Filter out abstract types and relationships.
    """
    # List of IFC classes that typically represent building elements
    element_patterns = [
        'IfcWall', 'IfcSlab', 'IfcBeam', 'IfcColumn', 'IfcDoor', 'IfcWindow',
        'IfcStair', 'IfcRamp', 'IfcRoof', 'IfcFooting', 'IfcPile', 'IfcMember',
        'IfcCovering', 'IfcCurtainWall', 'IfcPlate', 'IfcFurniture', 'IfcFurnishing',
        'IfcDistributionElement', 'IfcBuildingElement', 'IfcFlowTerminal',
        'IfcFlowSegment', 'IfcFlowController', 'IfcFlowFitting', 'IfcFlowMovingDevice',
        'IfcSpace', 'IfcBuildingStorey', 'IfcBuilding', 'IfcSite'
    ]

    # Check if the class matches any element pattern
    return any(pattern in ifc_class for pattern in element_patterns)


def print_analysis_results(analysis: Dict) -> None:
    """Print the analysis results in a formatted way."""

    print("=" * 80)
    print("IFC MODEL ELEMENT ANALYSIS")
    print("=" * 80)

    # Model information
    model_info = analysis['model_info']
    print(f"\nMODEL INFORMATION:")
    print(f"  File: {model_info['file_path']}")
    print(f"  Schema: {model_info['schema']}")
    print(f"  Total Building Elements: {model_info['total_elements']}")
    print(f"  Total IFC Entities: {model_info['total_entities']} (including geometric primitives)")

    # Summary
    summary = analysis['summary']
    print(f"\nSUMMARY:")
    print(f"  Different Element Types: {summary['total_element_types']}")
    print(f"  Type Objects: {summary['total_type_objects']}")
    print(f"  Classification Systems: {summary['total_classification_systems']}")

    print(f"\nTOP 10 MOST COMMON ELEMENT TYPES:")
    for element_type, count in summary['most_common_elements']:
        print(f"  {element_type}: {count} instances")

    # Classification systems
    if analysis['classification_systems']:
        print(f"\nCLASSIFICATION SYSTEMS FOUND:")
        for system in analysis['classification_systems']:
            print(f"  - {system}")

    # Detailed element types
    print(f"\nDETAILED ELEMENT TYPES:")
    print("-" * 80)

    for ifc_class, info in sorted(analysis['element_types'].items()):
        print(f"\n{ifc_class}")
        print(f"  Count: {info['count']}")

        if info['predefined_types']:
            print(f"  Predefined Types: {', '.join(info['predefined_types'])}")

        if info['type_objects']:
            print(f"  Type Objects: {', '.join(info['type_objects'])}")

        if info['classifications']:
            print(f"  Classifications: {', '.join(info['classifications'][:5])}")
            if len(info['classifications']) > 5:
                print(f"    ... and {len(info['classifications']) - 5} more")

        if info['sample_elements']:
            print(f"  Sample Elements:")
            for sample in info['sample_elements']:
                name = sample['name'] if sample['name'] else 'Unnamed'
                print(f"    ID: {sample['id']}, Name: {name}, GUID: {sample['guid']}")

    # Type objects
    if analysis['type_objects']:
        print(f"\n\nTYPE OBJECTS:")
        print("-" * 80)

        for type_class, info in sorted(analysis['type_objects'].items()):
            print(f"\n{type_class}")
            print(f"  Count: {info['count']}")
            print(f"  Occurrences: {len(info['occurrences'])}")

            if info['predefined_types']:
                print(f"  Predefined Types: {', '.join(info['predefined_types'])}")


def main():
    """Main function to run the analysis."""

    # Default to city_house_munich arc.ifc file
    default_path = "./src/experiment/bim_models/city_house_munich/arc.ifc"

    # Allow command line argument for different file
    if len(sys.argv) > 1:
        model_path = sys.argv[1]
    else:
        model_path = default_path

    print(f"Analyzing IFC model: {model_path}")

    try:
        analysis = analyze_ifc_elements(model_path)
        print_analysis_results(analysis)

        print(f"\n" + "=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()