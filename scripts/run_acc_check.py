"""
Script to run Solibri ACC check for one or all models.
Uses pre-configured SMC files (model + rules + classifications bundled).

Usage:
    Full check:          uv run python scripts/run_acc_check.py dental_clinic
    All models:          uv run python scripts/run_acc_check.py --all
    Skip existing:       uv run python scripts/run_acc_check.py --all --skip-existing
    Process only:        uv run python scripts/run_acc_check.py dental_clinic --process
    Enrich only:         uv run python scripts/run_acc_check.py dental_clinic --enrich
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

import ifcopenshell
from config import ACC_RES_PATH, ACC_MODELS_PATH
from src.acc.AutorunGenerator import generate_autorun
from src.acc.SolibriManagerMac import SolibriManagerMac
from src.acc.BcfHandler import process_bcf_for_model


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


def get_all_models() -> List[str]:
    """Return sorted list of model folder names that contain an .smc file."""
    models_dir = Path(ACC_MODELS_PATH)
    return sorted(
        p.parent.name
        for p in models_dir.glob("*/*.smc")
        if p.is_file() and not p.name.startswith("~$")
    )


def has_results(model_name: str) -> bool:
    """Check if a model already has BCF results."""
    bcf_dir = Path(ACC_RES_PATH) / model_name / "bcfzip"
    return bcf_dir.exists() and any(bcf_dir.iterdir())


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
    parser = argparse.ArgumentParser(description="Run Solibri ACC check for BIM models.")
    parser.add_argument("model", nargs="?", help="Model directory name (e.g. dental_clinic)")
    parser.add_argument("--all", action="store_true", help="Process all models in acc/bim_models/")
    parser.add_argument("--skip-existing", action="store_true", help="Skip models that already have BCF results")
    parser.add_argument("--process", action="store_true", help="Process BCF + enrich only (no Solibri)")
    parser.add_argument("--enrich", action="store_true", help="Enrich existing topics.json only")

    args = parser.parse_args()

    if not args.model and not args.all:
        parser.print_help()
        sys.exit(1)

    # Build list of models to process
    if args.all:
        models = get_all_models()
        if not models:
            print("No models found in acc/bim_models/")
            sys.exit(1)
        print(f"Found {len(models)} models: {', '.join(models)}\n")
    else:
        models = [args.model]

    failed: List[str] = []
    for model in models:
        if args.skip_existing and has_results(model):
            print(f"[Skipped] {model} (results exist)")
            continue

        if args.enrich:
            print(f"\nEnriching topics for: {model}")
            enrich_topics_with_ifc_types(model)
        elif args.process:
            print(f"\nProcessing BCF for: {model}")
            process_bcf_for_model(model)
            print("\nEnriching with IFC types...")
            enrich_topics_with_ifc_types(model)
            print(f"\n[Done] Results in: acc/res/{model}/")
        else:
            if not run_check(model):
                failed.append(model)

    if failed:
        print(f"\nFailed models: {', '.join(failed)}")
        sys.exit(1)

