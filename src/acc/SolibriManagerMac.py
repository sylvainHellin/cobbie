"""
Solibri Manager Module for macOS
Manages all Solibri operations including:
- Settings management (stub for future plist implementation)
- Autorun execution and process monitoring
- Result cleanup and organization
"""

import os
import sys
import time
import psutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

# Add src directory to Python path for imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import ROOT_PATH, ACC_ROOT_PATH, ACC_RES_PATH, ACC_SETUP_PATH


class SolibriSettingsManager:
    """
    Manages Solibri 3D viewer settings on macOS.
    Currently a stub - stores settings in memory only.
    Future implementation will use plist files.
    """
    
    def __init__(self):
        self.backup_dir = ACC_ROOT_PATH
        
        # Default settings template
        self.settings: Dict[str, Optional[str]] = {
            "back-clip-distance": None,
            "front-clip-distance": None,
            "field-of-view": None,
            "height-of-eyes": None
        }
    
    def read_settings(self) -> Dict[str, Optional[str]]:
        """
        Read current settings.
        
        Returns:
            Dictionary of setting names to values
        """
        # TODO: Implement plist reading for macOS
        print("Note: Settings reading not yet implemented on macOS")
        return self.settings
    
    def update_settings(self, new_values: Dict[str, str]):
        """
        Update settings with new values.
        
        Args:
            new_values: Dictionary of settings to update
        """
        # TODO: Implement plist writing for macOS
        print("Note: Settings modification not yet implemented on macOS")
        self.settings.update(new_values)  # type: ignore
    
    def restore_settings(self):
        """Restore original settings from backup."""
        # TODO: Implement plist restoration for macOS
        print("Note: Settings restoration not yet implemented on macOS")


class SolibriExecutor:
    """
    Handles Solibri autorun execution and process monitoring on macOS.
    """
    
    SOLIBRI_PATH = Path("/Applications/Solibri/Solibri.app/Contents/MacOS/JavaApplicationStub")
    PROCESS_NAME = "JavaApplicationStub"
    
    def __init__(self):
        self.res_dir = ACC_RES_PATH
    
    def cleanup_result_folders(self):
        """
        Delete previous result files before running Solibri.
        Cleans: .bcfzip, .json and .smc files in acc/res (only if folders exist).
        """
        patterns = [
            (os.path.join(self.res_dir, "bcfzip"), ".bcfzip"),  # type: ignore
            (os.path.join(self.res_dir, "issues"), ".json"),  # type: ignore
            (os.path.join(self.res_dir, "smc"), ".smc"),  # type: ignore
        ]
        
        for folder, ext in patterns:
            if not os.path.isdir(folder):
                continue
            for filename in os.listdir(folder):
                if filename.lower().endswith(ext):
                    try:
                        os.remove(os.path.join(folder, filename))
                    except Exception as e:
                        print(f"Warning: Could not delete {filename} in {folder}: {e}")
    
    def run_autorun(self, autorun_xml: str) -> bool:
        """
        Execute Solibri with autorun XML configuration.
        
        Args:
            autorun_xml: Absolute path to autorun XML file
        
        Returns:
            True if successful, False otherwise
        """
        autorun_xml = os.path.abspath(autorun_xml)
        
        if not os.path.exists(autorun_xml):
            print(f"Error: Autorun XML not found: {autorun_xml}")
            return False
        
        if not self.SOLIBRI_PATH.exists():
            print(f"Error: Solibri not found at: {self.SOLIBRI_PATH}")
            return False
        
        cmd = [str(self.SOLIBRI_PATH), "--autorun", autorun_xml]
        
        process = subprocess.Popen(cmd)
        self._monitor_process(process)
        
        return True
    
    def _monitor_process(self, process: subprocess.Popen):
        """
        Monitor a subprocess until it exits.
        
        Args:
            process: Subprocess to monitor
        """
        while process.poll() is None:
            time.sleep(5)
    
    def wait_for_solibri_exit(self):
        """Wait until Solibri process completely exits."""
        print("\033[1m\033[92m [Solibri Execution] \033[0m running...")
        
        while any(proc.name() == self.PROCESS_NAME 
                  for proc in psutil.process_iter()):
            time.sleep(1)


class SolibriManagerMac:
    """
    High-level manager for Solibri operations on macOS.
    Supports both IFC and SMC model modes.
    """
    
    def __init__(self, settings: Optional[Dict[str, str]] = None):
        """
        Initialize Solibri manager.
        
        Args:
            settings: Default Solibri 3D settings (from env or config)
        """
        self.project_root = Path(ROOT_PATH)
        self.settings_manager = SolibriSettingsManager()
        self.executor = SolibriExecutor()
        
        # Default settings
        self.settings = settings or self._load_default_settings()
    
    def _load_default_settings(self) -> Dict[str, str]:
        """
        Load default Solibri 3D settings from environment variables.
        
        Returns:
            Dictionary of setting names to values
        """
        return {
            "back-clip-distance": os.getenv("SOLIBRI_BACK_CLIP_DISTANCE", "100000.0"),
            "front-clip-distance": os.getenv("SOLIBRI_FRONT_CLIP_DISTANCE", "50000.0"),
            "height-of-eyes": os.getenv("SOLIBRI_HEIGHT_OF_EYES", "2500.0"),
            "field-of-view": os.getenv("SOLIBRI_FIELD_OF_VIEW", "35.0"),
        }
    
    def get_autorun_xml_path(self) -> Path:
        """
        Get path to autorun XML configuration file.
        
        Returns:
            Path to autorun_setting.xml
        """
        return Path(ACC_SETUP_PATH) / "autorun_setting.xml"
    
    def execute_check(
        self,
        autorun_xml: Optional[str] = None,
        update_settings: bool = True
    ) -> bool:
        """
        Execute complete Solibri checking workflow.
        
        Args:
            autorun_xml: Path to autorun XML (auto-detected if None)
            update_settings: Whether to update settings before execution
        
        Returns:
            True if successful, False otherwise
        """
        # Cleanup old results
        self.executor.cleanup_result_folders()
        
        # Update Solibri 3D settings
        if update_settings:
            self.settings_manager.update_settings(self.settings)
        
        # Get autorun XML path
        if autorun_xml is None:
            autorun_xml = str(self.get_autorun_xml_path())
        
        # Execute autorun
        success = self.executor.run_autorun(autorun_xml)
        
        print(f"\033[1m\033[92m [Solibri Execution] \033[0m {'started' if success else 'failed'}")
        
        if success:
            # Wait for Solibri to complete
            self.executor.wait_for_solibri_exit()
            print("\033[1m\033[92m [Solibri Execution] \033[0m completed")
        
        return success
    
    def update_settings(self, new_settings: Dict[str, str]):
        """
        Update Solibri 3D settings.
        
        Args:
            new_settings: Dictionary of settings to update
        """
        self.settings.update(new_settings)
        self.settings_manager.update_settings(self.settings)
    
    def restore_original_settings(self):
        """Restore original Solibri settings from backup."""
        self.settings_manager.restore_settings()


# Standalone function for backward compatibility
def run_solibri_check(
    autorun_xml: Optional[str] = None,
    settings: Optional[Dict[str, str]] = None
) -> bool:
    """
    Simplified function to run Solibri check.
    
    Args:
        autorun_xml: Path to autorun XML file
        settings: Solibri 3D settings
    
    Returns:
        True if successful, False otherwise
    """
    manager = SolibriManagerMac(settings=settings)
    return manager.execute_check(autorun_xml)
