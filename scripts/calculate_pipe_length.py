#!/usr/bin/env python3
"""
Script to calculate the total length of pipes in the MEP IFC model.

This script:
1. Loads the mep.ifc file
2. Finds all elements of type IfcFlowSegment
3. Filters for elements in the M-PIPE layer
4. Extracts the length from PSet_Revit_Dimensions
5. Calculates and displays the total length

Usage:
    uv run python scripts/calculate_pipe_length.py
"""

import ifcopenshell
import ifcopenshell.util.element
from pathlib import Path

def calculate_total_pipe_length(ifc_file_path: str) -> float:
    """
    Calculate the total length of mechanical pipes in an IFC file.

    This script looks for IfcFlowSegment elements that represent mechanical pipes
    (not ducts) and calculates their total length using PSet_Revit_Dimensions.

    Args:
        ifc_file_path: Path to the IFC file

    Returns:
        Total length of mechanical pipes (in the units used in the IFC file)
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_file_path)

    total_length = 0.0
    mechanical_pipe_count = 0
    duct_count = 0
    total_length_ducts = 0.0

    # Get all IfcFlowSegment elements (pipes and ducts in MEP)
    flow_segments = model.by_type("IfcFlowSegment")

    print(f"Found {len(flow_segments)} IfcFlowSegment elements")
    print("\nProcessing all flow segments...")

    for segment in flow_segments:
        # Get the element name to identify if it's a mechanical pipe or duct
        element_name = getattr(segment, 'Name', 'Unknown')

        # Get property sets
        psets = ifcopenshell.util.element.get_psets(segment)

        # Look for PSet_Revit_Dimensions
        revit_dimensions = psets.get("PSet_Revit_Dimensions", {})

        # Try to get the length property
        length = None
        if "Length" in revit_dimensions:
            length = revit_dimensions["Length"]

        if length is not None:
            try:
                length_value = float(length)

                # Categorize based on element name
                if "Pipe" in element_name and "Duct" not in element_name:
                    # This is a mechanical pipe
                    total_length += length_value
                    mechanical_pipe_count += 1
                    print(f"  ✓ Mechanical Pipe: {element_name} - Length: {length_value}")

                    # Show additional details
                    if "Size" in revit_dimensions:
                        print(f"    Size: {revit_dimensions['Size']}")
                    if "Outer Diameter" in revit_dimensions:
                        print(f"    Outer Diameter: {revit_dimensions['Outer Diameter']}")

                elif "Duct" in element_name:
                    # This is a duct (HVAC)
                    total_length_ducts += length_value
                    duct_count += 1
                    # We don't print ducts by default to avoid clutter, but count them

                else:
                    # Unclear type, show for debugging
                    print(f"  ? Other: {element_name} - Length: {length_value}")

            except (ValueError, TypeError):
                print(f"  ⚠ Warning: Could not parse length value '{length}' for {element_name}")
        else:
            # Show elements without length for debugging
            if "Pipe" in element_name or "Duct" in element_name:
                print(f"  - No length: {element_name}")

    print(f"\n" + "="*60)
    print(f"RESULTS SUMMARY")
    print(f"="*60)
    print(f"Mechanical Pipes:")
    print(f"  - Count: {mechanical_pipe_count}")
    print(f"  - Total Length: {total_length:.4f}")
    if mechanical_pipe_count > 0:
        print(f"  - Average Length: {total_length / mechanical_pipe_count:.4f}")

    print(f"\nHVAC Ducts:")
    print(f"  - Count: {duct_count}")
    print(f"  - Total Length: {total_length_ducts:.4f}")
    if duct_count > 0:
        print(f"  - Average Length: {total_length_ducts / duct_count:.4f}")

    print(f"\nAll Flow Segments:")
    print(f"  - Total: {len(flow_segments)}")
    print(f"  - Processed: {mechanical_pipe_count + duct_count}")
    print(f"  - Uncategorized: {len(flow_segments) - mechanical_pipe_count - duct_count}")

    return total_length

def main():
    """Main function to run the pipe length calculation."""
    # Path to the MEP IFC file for the duplex project
    ifc_file_path = "src/experiment/bim_models/duplex/mep.ifc"

    # Check if the file exists
    if not Path(ifc_file_path).exists():
        print(f"Error: IFC file not found at '{ifc_file_path}'")
        print("Please ensure the mep.ifc file is in the correct location.")
        return 1

    print(f"Calculating pipe lengths for: {ifc_file_path}")
    print("=" * 60)

    try:
        total_length = calculate_total_pipe_length(ifc_file_path)
        print(f"\nTotal pipe length in MEP model: {total_length}")
        return 0
    except Exception as e:
        print(f"Error processing IFC file: {e}")
        return 1

if __name__ == "__main__":
    exit(main())