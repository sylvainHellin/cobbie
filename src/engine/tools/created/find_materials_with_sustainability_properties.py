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
import re


def find_materials_with_sustainability_properties(
    ifc_file_path: str, sustainability_keywords: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Systematically searches through all material representations in an IFC model to identify materials
    with sustainability-related properties.

    This function handles various IFC material entity types and searches across all property sets
    associated with materials using pattern matching to identify sustainability-related properties.

    Assumptions:
    - Works with IFC2X3, IFC4, and IFC4X3 schemas
    - Handles materials from various BIM authoring software including Revit, ArchiCAD, Tekla, etc.
    - Looks for properties in standard property sets as well as software-specific ones (e.g., PSet_Revit_Dimensions)

    Args:
        ifc_file_path (str): Path to the IFC file to analyze
        sustainability_keywords (List[str], optional): Custom keywords to search for sustainability properties.
            If not provided, defaults to common sustainability terms.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing information about a material with
        sustainability properties:
        - material_name (str): Name of the material
        - material_type (str): Type of material representation (IfcMaterial, IfcMaterialLayer, etc.)
        - element_type (str, optional): If material is associated with specific elements, the element type
        - property_name (str): Name of the sustainability property found
        - property_value (Any): Value of the sustainability property
        - property_set_name (str): Name of the property set containing the property
        - element_guid (str, optional): GUID of associated element if applicable
        - confidence_score (float): Confidence score (0-1) indicating how well the property matches sustainability keywords
    """

    # Default sustainability keywords if none provided
    if sustainability_keywords is None:
        sustainability_keywords = [
            "recycled",
            "recycle",
            "epd",
            "environmental",
            "carbon",
            "co2",
            "sustainable",
            "green",
            "eco",
            "renewable",
            "reused",
            "lca",
            "life cycle",
            "embodied",
            "gwp",
            "global warming",
            "footprint",
            "declaration",
            "certification",
            "cradle",
            "hcfc",
            "ozone",
            "voc",
        ]

    # Open the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)

    # Results list
    results = []

    # Get all materials and related entities based on schema
    material_entities = []

    # Try to get different material entity types, handling schema differences
    try:
        material_entities.extend(ifc_file.by_type("IfcMaterial"))
    except:
        pass

    try:
        material_entities.extend(ifc_file.by_type("IfcMaterialLayer"))
    except:
        pass

    try:
        material_entities.extend(ifc_file.by_type("IfcMaterialLayerSet"))
    except:
        pass

    try:
        material_entities.extend(ifc_file.by_type("IfcMaterialLayerSetUsage"))
    except:
        pass

    try:
        material_entities.extend(ifc_file.by_type("IfcMaterialList"))
    except:
        pass

    # Try to get IfcMaterialConstituent if available (IFC4+)
    try:
        material_entities.extend(ifc_file.by_type("IfcMaterialConstituent"))
    except:
        pass

    try:
        material_entities.extend(ifc_file.by_type("IfcMaterialConstituentSet"))
    except:
        pass

    # Process each material entity
    for material in material_entities:
        material_type = material.is_a()
        material_name = getattr(material, "Name", f"Unnamed {material_type}")

        # Get associated elements if possible
        element_type = None
        element_guid = None

        try:
            # Try to find elements that use this material
            elements = ifcopenshell.util.element.get_elements_by_material(
                ifc_file, material
            )
            if elements:
                first_element = list(elements)[0]
                element_type = first_element.is_a()
                element_guid = getattr(first_element, "GlobalId", None)
        except:
            pass

        # Get property sets for this material
        try:
            psets = ifcopenshell.util.element.get_psets(material)
        except:
            # If get_psets fails, try to get them manually
            psets = {}
            try:
                # Try to get property sets directly related to material
                if hasattr(material, "HasProperties"):
                    for prop_def in material.HasProperties:
                        if prop_def.is_a() == "IfcPropertySet":
                            pset_dict = {}
                            if hasattr(prop_def, "HasProperties"):
                                for prop in prop_def.HasProperties:
                                    if hasattr(prop, "Name") and hasattr(
                                        prop, "NominalValue"
                                    ):
                                        pset_dict[prop.Name] = getattr(
                                            prop.NominalValue,
                                            "wrappedValue",
                                            str(prop.NominalValue),
                                        )
                            psets[prop_def.Name] = pset_dict
            except:
                pass

        # Search through property sets for sustainability properties
        for pset_name, properties in psets.items():
            if isinstance(properties, dict):
                for prop_name, prop_value in properties.items():
                    # Check if property name matches sustainability keywords
                    confidence_score = _calculate_confidence_score(
                        prop_name, sustainability_keywords
                    )

                    if confidence_score > 0:
                        result = {
                            "material_name": material_name,
                            "material_type": material_type,
                            "property_name": prop_name,
                            "property_value": prop_value,
                            "property_set_name": pset_name,
                            "confidence_score": confidence_score,
                        }

                        # Add optional fields if available
                        if element_type:
                            result["element_type"] = element_type
                        if element_guid:
                            result["element_guid"] = element_guid

                        results.append(result)

    # Also check materials associated with elements
    try:
        # Get all products that might have materials
        products = ifc_file.by_type("IfcProduct")
        processed_materials = set()  # To avoid duplicates

        for product in products:
            try:
                materials = ifcopenshell.util.element.get_materials(product)
                if materials:
                    for material in materials:
                        material_id = (
                            material.id() if hasattr(material, "id") else id(material)
                        )
                        if material_id in processed_materials:
                            continue
                        processed_materials.add(material_id)

                        material_type = (
                            material.is_a()
                            if hasattr(material, "is_a")
                            else str(type(material))
                        )
                        material_name = getattr(
                            material, "Name", f"Unnamed {material_type}"
                        )

                        # Get property sets
                        try:
                            psets = ifcopenshell.util.element.get_psets(material)
                        except:
                            psets = {}

                        # Search through property sets for sustainability properties
                        for pset_name, properties in psets.items():
                            if isinstance(properties, dict):
                                for prop_name, prop_value in properties.items():
                                    confidence_score = _calculate_confidence_score(
                                        prop_name, sustainability_keywords
                                    )

                                    if confidence_score > 0:
                                        result = {
                                            "material_name": material_name,
                                            "material_type": material_type,
                                            "element_type": product.is_a(),
                                            "element_guid": product.GlobalId,
                                            "property_name": prop_name,
                                            "property_value": prop_value,
                                            "property_set_name": pset_name,
                                            "confidence_score": confidence_score,
                                        }
                                        results.append(result)
                        # Also check direct properties of the material
                        if hasattr(material, "HasProperties"):
                            for prop_def in material.HasProperties:
                                if hasattr(prop_def, "Name") and hasattr(
                                    prop_def, "NominalValue"
                                ):
                                    prop_name = prop_def.Name
                                    prop_value = getattr(
                                        prop_def.NominalValue,
                                        "wrappedValue",
                                        str(prop_def.NominalValue),
                                    )
                                    confidence_score = _calculate_confidence_score(
                                        prop_name, sustainability_keywords
                                    )

                                    if confidence_score > 0:
                                        result = {
                                            "material_name": material_name,
                                            "material_type": material_type,
                                            "element_type": product.is_a(),
                                            "element_guid": product.GlobalId,
                                            "property_name": prop_name,
                                            "property_value": prop_value,
                                            "property_set_name": "DirectMaterialProperties",
                                            "confidence_score": confidence_score,
                                        }
                                        results.append(result)
            except:
                continue
    except:
        pass

    return results


def _calculate_confidence_score(property_name: str, keywords: List[str]) -> float:
    """
    Calculate confidence score based on how well property name matches sustainability keywords.

    Args:
        property_name (str): Name of the property to check
        keywords (List[str]): List of sustainability keywords to match against

    Returns:
        float: Confidence score between 0 and 1
    """
    if not property_name or not keywords:
        return 0.0

    property_name_lower = property_name.lower()
    max_score = 0.0

    for keyword in keywords:
        keyword_lower = keyword.lower()
        # Exact match gets highest score
        if keyword_lower == property_name_lower:
            return 1.0
        # Partial match scoring
        elif keyword_lower in property_name_lower:
            # Score based on how much of the property name is matched
            match_ratio = len(keyword_lower) / len(property_name_lower)
            score = 0.5 + (0.5 * match_ratio)  # Between 0.5 and 1.0
            max_score = max(max_score, score)
        # Check if keyword is part of property name (word boundary)
        elif re.search(r"\b" + re.escape(keyword_lower) + r"\b", property_name_lower):
            score = 0.7
            max_score = max(max_score, score)

    return max_score
