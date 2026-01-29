"""
Simple script to run Solibri ACC check for a model.
Uses pre-configured SMC files (model + rules + classifications bundled).

Usage:
    Full check:    uv run python scripts/run_acc_check.py <model_name>
    Process only:  uv run python scripts/run_acc_check.py <model_name> --process
    Enrich only:   uv run python scripts/run_acc_check.py <model_name> --enrich

Example: uv run python scripts/run_acc_check.py dental_clinic
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any

import ifcopenshell

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config import ACC_RES_PATH, ACC_MODELS_PATH
from acc.AutorunGenerator import generate_autorun
from acc.SolibriManagerMac import SolibriManagerMac
from acc.BcfHandler import process_bcf_for_model


def enrich_topics_with_ifc_types(model_name: str) -> Path:
    """
    Enrich topics.json with IFC element type info for each GUID.
    
    Args:
        model_name: Name of the model directory
    
    Returns:
        Path to updated topics.json
    """
    # Paths
    model_dir = Path(ACC_MODELS_PATH) / model_name
    topics_path = Path(ACC_RES_PATH) / model_name / "issues" / "topics.json"
    
    # Find SMC file first, IFC has the same base name
    smc_files = [f for f in model_dir.glob("*.smc") if not f.name.startswith("~$")]
    if not smc_files:
        raise FileNotFoundError(f"No SMC file found in {model_dir}")
    
    smc_name = smc_files[0].stem  # e.g., "arc" from "arc.smc"
    ifc_path = model_dir / f"{smc_name}.ifc"
    
    if not ifc_path.exists():
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")
    
    print(f"  Loading IFC: {ifc_path.name}")
    ifc_model = ifcopenshell.open(str(ifc_path))
    
    # Load topics
    with open(topics_path, "r", encoding="utf-8") as f:
        topics: List[Dict[str, Any]] = json.load(f)
    
    print(f"  Enriching {len(topics)} topics...")
    
    # Build GUID -> element type cache
    guid_types: Dict[str, str] = {}
    
    for topic in topics:
        enriched_guids = []
        for guid in topic.get("ifc_guids", []):
            if guid not in guid_types:
                try:
                    element = ifc_model.by_guid(guid)
                    guid_types[guid] = element.is_a() if element else "Unknown"
                except Exception:
                    guid_types[guid] = "NotFound"
            
            enriched_guids.append({
                "guid": guid,
                "ifc_type": guid_types[guid]
            })
        
        topic["ifc_guids_enriched"] = enriched_guids
    
    # Save enriched topics
    with open(topics_path, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2, sort_keys=True)
    
    # Stats
    type_counts: Dict[str, int] = {}
    for t in guid_types.values():
        type_counts[t] = type_counts.get(t, 0) + 1
    
    print(f"  Enriched with {len(guid_types)} unique GUIDs")
    print(f"  Types: {dict(sorted(type_counts.items(), key=lambda x: -x[1]))}")
    
    return topics_path


def run_check(model_name: str) -> bool:
    """
    Run Solibri check for a model.
    
    Args:
        model_name: Name of the model directory (e.g., 'duplex', 'dental_clinic')
    
    Returns:
        True if successful
    """
    print(f"\n{'='*60}")
    print(f"Running ACC check for: {model_name}")
    print(f"{'='*60}\n")
    
    # Generate autorun config
    autorun_path = generate_autorun(model_name)
    
    # Run Solibri
    manager = SolibriManagerMac()
    success = manager.execute_check(str(autorun_path))
    
    if not success:
        return False
    
    # Extract BCF and create topics.json
    print("\nProcessing BCF results...")
    process_bcf_for_model(model_name)
    
    # Enrich with IFC element types
    print("\nEnriching with IFC types...")
    enrich_topics_with_ifc_types(model_name)
    
    print(f"\n[Done] Results in: acc/res/{model_name}/")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Full check:    uv run python scripts/run_acc_check.py <model_name>")
        print("  Process only:  uv run python scripts/run_acc_check.py <model_name> --process")
        print("  Enrich only:   uv run python scripts/run_acc_check.py <model_name> --enrich")
        print("\nExample: uv run python scripts/run_acc_check.py dental_clinic")
        sys.exit(1)
    
    model = sys.argv[1]
    flag = sys.argv[2] if len(sys.argv) > 2 else None
    
    if flag == "--enrich":
        # Enrich existing topics.json only
        print(f"\nEnriching topics for: {model}")
        enrich_topics_with_ifc_types(model)
        sys.exit(0)
    
    if flag == "--process":
        # Process BCF + enrich (no Solibri)
        print(f"\nProcessing BCF for: {model}")
        process_bcf_for_model(model)
        print("\nEnriching with IFC types...")
        enrich_topics_with_ifc_types(model)
        print(f"\n[Done] Results in: acc/res/{model}/")
        sys.exit(0)
    
    success = run_check(model)
    sys.exit(0 if success else 1)

