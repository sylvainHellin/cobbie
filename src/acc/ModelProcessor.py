"""
Model Processor Module
Orchestrates the complete BIM model checking pipeline:
- Pre-check: Copy IFC models to Solibri working directory
- Run-check: Execute Solibri batch with monitoring
- Post-check: Copy results to organized folders
- Multi-model processing support
"""

import os
import sys
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Union, Dict, Any
from dataclasses import dataclass

# Add src directory to Python path for imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import ACC_RES_PATH, ACC_MODELS_PATH

@dataclass
class ModelPaths:
    """Container for model-related file paths."""
    source_dir: Path
    working_dir: Path
    results_dir: Path
    model_filename: str
    
    @property
    def model_name(self) -> str:
        """Get model name without extension."""
        return Path(self.model_filename).stem
    
    @property
    def source_path(self) -> Path:
        """Full path to source IFC file."""
        return self.source_dir / self.model_filename
    
    @property
    def working_path(self) -> Path:
        """Full path to working directory IFC file."""
        return self.working_dir / "model.ifc"


class ModelFileManager:
    """
    Manages file operations for IFC models.
    Handles copying models to/from working directories and organizing results.
    """
    
    def __init__(self) -> None:
        """Initialize file manager."""
        self.acc_working_dir_res = Path(ACC_RES_PATH)
        self.acc_working_dir_models = Path(ACC_MODELS_PATH)
        self.data_processed_ifc_dir = Path(ACC_MODELS_PATH)
        self.data_processes_acc_res_dir = Path(ACC_RES_PATH)
    
    @staticmethod
    def _ensure_path(path_result: Union[Path, Dict[str, Path]]) -> Path:
        """Ensure result is a Path, not a dictionary."""
        if isinstance(path_result, dict):
            raise ValueError("Expected a single path, but got a dictionary")
        return path_result
    
    def get_all_ifc_models(self) -> List[str]:
        """
        Get list of all IFC files in the models directory and all subdirectories.
        
        Returns:
            Sorted list of IFC file paths (relative to data_processed_ifc_dir)
        """
        if not self.data_processed_ifc_dir.exists():
            return []
        
        ifc_files: List[str] = []
        
        # Only look for .ifc files directly under the base directory (no recursion)
        for ifc_path in self.data_processed_ifc_dir.glob("*.ifc"):
            if ifc_path.is_file():
                # Get relative path from base directory
                relative_path = ifc_path.relative_to(self.data_processed_ifc_dir)
                # Convert to string with forward slashes for cross-platform compatibility
                ifc_files.append(str(relative_path).replace('\\', '/'))
        
        return sorted(ifc_files)
    
    def copy_model_to_working(self, model_filename: str) -> bool:
        """
        Copy IFC model to Solibri's working directory as 'model.ifc'.
        
        Args:
            model_filename: Name of the IFC file to copy
        
        Returns:
            True if successful, False otherwise
        """
        source: Path = self.data_processed_ifc_dir / model_filename
        target: Path = self.acc_working_dir_models / "model.ifc"
        
        if not source.exists():
            print(f"\033[1m\033[91m Error: \033[0m Model file not found: {source}")
            return False
        
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(target))
            print(f"\033[1m\033[92m [Data Update] \033[0m IFC model {model_filename} copied to working directory")
            return True
        except Exception as e:
            print(f"\033[1m\033[91m Error copying model: \033[0m {e}")
            return False
    
    def copy_results_to_storage(self, model_filename: str) -> bool:
        """
        Copy checking results from Solibri output to organized storage folders.
        Creates subfolders per model using model name (without extension).
        
        Args:
            model_filename: Name of the model being processed
        
        Returns:
            True if successful, False otherwise
        """
        model_name: str = Path(model_filename).stem
        
        # Source directories (Solibri output)
        sources: Dict[str, Path] = {
            "smc": self.acc_working_dir_res / "smc",
            "bcfzip": self.acc_working_dir_res / "bcfzip",
            "issues": self.acc_working_dir_res / "issues",
        }
        
        # Target directories (organized by model name - subtypes)
        targets: Dict[str, Path] = {
            "smc": self.data_processes_acc_res_dir / model_name / "smc",
            "bcfzip": self.data_processes_acc_res_dir / model_name / "bcfzip",
            "issues": self.data_processes_acc_res_dir / model_name / "issues",
        }
        
        success: bool = True
        for result_type, source_dir in sources.items():
            target_dir = targets[result_type]
            
            if not self._copy_folder_content(source_dir, target_dir, result_type):
                success = False
        
        if success:
            print(f"\033[1m\033[92m [Results Copied] \033[0m Model: {model_name}")
        
        return success
    
    def _copy_folder_content(self, source_dir: Path, target_dir: Path, label: str) -> bool:
        """
        Copy all files from source directory to target directory.
        
        Args:
            source_dir: Source directory path
            target_dir: Target directory path
            label: Label for logging
        
        Returns:
            True if successful, False otherwise
        """
        if not source_dir.is_dir():
            print(f"\033[1m\033[93m Warning: \033[0m {label} folder not found at: {source_dir}")
            return False
        
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            
            for item in source_dir.iterdir():
                if item.is_file():
                    src_file = item
                    dst_file = target_dir / item.name
                    shutil.copy2(str(src_file), str(dst_file))
            
            return True
            
        except Exception as e:
            print(f"\033[1m\033[91m Error copying {label}: \033[0m {e}")
            return False
    
    def verify_results_exist(self, model_filename: str) -> Tuple[bool, List[str]]:
        """
        Check if results already exist for a model.
        
        Args:
            model_filename: Name of the model to check (can include subdirectory path)
        
        Returns:
            Tuple of (all_exist: bool, missing_types: List[str])
        """
        # Extract model name from filename (handle subdirectory paths)
        # e.g., "case-autcon/case-autcon.ifc" -> "case-autcon"
        model_name: str = Path(model_filename).stem
        
        result_types: List[str] = ["smc", "bcfzip", "issues"]
        missing: List[str] = []
        
        for result_type in result_types:
            result_dir: Path = self.data_processes_acc_res_dir / model_name / result_type
            
            # Check if directory exists and has actual files
            if not result_dir.exists():
                missing.append(result_type)
            else:
                # Check if directory has any files (not just subdirectories)
                has_files: bool = any(
                    item.is_file()
                    for item in result_dir.iterdir()
                )
                if not has_files:
                    missing.append(result_type)
        
        return (len(missing) == 0, missing)


class ModelProcessor:
    """
    High-level orchestrator for the complete model checking pipeline.
    Coordinates pre-check, execution, and post-check operations.
    """
    
    def __init__(
        self, 
        solibri_manager: Optional[Any] = None,  # Will be imported/injected
    ) -> None:
        """
        Initialize model processor.
        
        Args:
            solibri_manager: Instance of SolibriManager (optional, for dependency injection)
        """
        self.file_manager: ModelFileManager = ModelFileManager()
        self.solibri_manager: Optional[Any] = solibri_manager
    
    def process_single_model(
        self, 
        model_filename: str,
        skip_if_exists: bool = False
    ) -> bool:
        """
        Process a single IFC model through the complete pipeline.
        
        Args:
            model_filename: Name of the IFC file to process
            skip_if_exists: Skip processing if results already exist
        
        Returns:
            True if successful, False otherwise
        """
        print(f"\n{'='*60}")
        print(f"Processing model: {model_filename}")
        print(f"{'='*60}")
        
        # Check if results already exist
        if skip_if_exists:
            all_exist, missing = self.file_manager.verify_results_exist(model_filename)
            if all_exist:
                print(f"\033[1m\033[93m [Skipped] \033[0m Results already exist for {model_filename}")
                return True
            elif missing:
                print(f"\033[1m\033[94m [Info] \033[0m Missing results: {', '.join(missing)}")
        
        # Execute pipeline steps in sequence
        steps: List[Tuple[str, Any, Optional[str], str]] = [
            ("PRE-CHECK", self.pre_check, model_filename, "Copy model to working directory"),
            ("RUN-CHECK", self.run_check, None, "Execute Solibri batch"),
            ("POST-CHECK", self.post_check, model_filename, "Copy results to storage"),
        ]
        
        for step_name, step_func, step_arg, step_description in steps:
            print(f"\033[1m\033[94m [{step_name}] \033[0m {step_description}...")
            success: bool = step_func(step_arg) if step_arg is not None else step_func()
            if not success:
                print(f"\033[1m\033[91m [{step_name} Failed] \033[0m {step_description}")
                return False
            print(f"\033[1m\033[92m [{step_name} Complete] \033[0m {step_description}")
        
        print(f"\033[1m\033[92m [Completed] \033[0m Model {model_filename} processed successfully")
        return True
    
    def process_multiple_models(
        self,
        model_filenames: Optional[List[str]] = None,
        skip_if_exists: bool = False
    ) -> List[str]:
        """
        Process multiple IFC models sequentially.
        
        Args:
            model_filenames: List of model filenames to process (None = all models)
            skip_if_exists: Skip models with existing results
        
        Returns:
            List of successfully processed model names
        """
        # Get models to process
        if model_filenames is None:
            model_filenames = self.file_manager.get_all_ifc_models()
        
        if not model_filenames:
            print("\033[1m\033[93m [Warning] \033[0m No IFC models found to process")
            return []
        
        print(f"\n{'='*60}")
        print(f"Processing {len(model_filenames)} models")
        print(f"{'='*60}\n")
        
        # Process each model
        successful: List[str] = []
        failed: List[str] = []
        
        for i, model_filename in enumerate(model_filenames, 1):
            print(f"\n[{i}/{len(model_filenames)}] Starting: {model_filename}")
            
            if self.process_single_model(model_filename, skip_if_exists):
                successful.append(model_filename)
            else:
                failed.append(model_filename)
        
        # Summary
        print(f"\n{'='*60}")
        print(f"Processing Complete")
        print(f"{'='*60}")
        print(f"\033[1m\033[92m Successful: \033[0m {len(successful)}")
        if failed:
            print(f"\033[1m\033[91m Failed: \033[0m {len(failed)}")
            for model in failed:
                print(f"  - {model}")
        
        return successful
    
    def pre_check(self, model_filename: str) -> bool:
        """
        PRE-CHECK: Copy IFC model to Solibri working directory.
        
        Args:
            model_filename: Name of the model to copy
        
        Returns:
            True if successful, False otherwise
        """
        return self.file_manager.copy_model_to_working(model_filename)
    
    def run_check(self) -> bool:
        """
        RUN-CHECK: Execute Solibri batch file.
        
        Returns:
            True if successful, False otherwise
        """
        if self.solibri_manager is None:
            print("\033[1m\033[91m Error: \033[0m SolibriManager not initialized")
            return False
        
        return self.solibri_manager.execute_check()
    
    def post_check(self, model_filename: str) -> bool:
        """
        POST-CHECK: Copy results to organized storage.
        
        Args:
            model_filename: Name of the model being processed
        
        Returns:
            True if successful, False otherwise
        """
        return self.file_manager.copy_results_to_storage(model_filename)


def process_all_models(
    solibri_manager: Any,
    model_filenames: Optional[List[str]] = None,
    skip_if_exists: bool = False
) -> List[str]:
    """
    Process multiple models through the complete pipeline.
    
    Args:
        solibri_manager: Instance of SolibriManager
        model_filenames: List of specific models to process (None = all)
        skip_if_exists: Skip models with existing results
    
    Returns:
        List of successfully processed model names
    """
    processor: ModelProcessor = ModelProcessor(solibri_manager)
    return processor.process_multiple_models(model_filenames, skip_if_exists)