"""
Autorun Generator Module
Generates dynamic autorun_setting.xml for Solibri batch processing.
Uses pre-configured SMC files that contain model + rules + classifications.
"""

from pathlib import Path
from typing import Optional
from config import ROOT_PATH, ACC_SETUP_PATH, ACC_RES_PATH, ACC_MODELS_PATH


class AutorunGenerator:
    """
    Generates Solibri autorun XML configuration for different models.
    Expects SMC files with pre-configured rules and classifications.
    """
    
    def __init__(self, model_name: str):
        """
        Initialize generator for a specific model.
        
        Args:
            model_name: Name of the model directory (e.g., 'duplex', 'dental_clinic')
        """
        self.model_name = model_name
        self.root_path = Path(ROOT_PATH)
        self.setup_path = Path(ACC_SETUP_PATH)
        
    @property
    def smc_path(self) -> Path:
        """Path to the pre-configured SMC file for this model."""
        model_dir = Path(ACC_MODELS_PATH) / self.model_name
        # Filter out temp files like ~$arc.smc
        smc_files = [f for f in model_dir.glob("*.smc") if not f.name.startswith("~$")]
        if not smc_files:
            raise FileNotFoundError(f"No SMC file found in {model_dir}")
        if len(smc_files) > 1:
            raise ValueError(f"Multiple SMC files found in {model_dir}: {[f.name for f in smc_files]}")
        return smc_files[0]
    
    @property
    def output_dir(self) -> Path:
        """Output directory for this model's results."""
        return Path(ACC_RES_PATH) / self.model_name
    
    @property
    def bcf_output_path(self) -> Path:
        """Path for BCF output file."""
        return self.output_dir / "bcfzip" / f"{self.model_name}_check.bcfzip"
    
    @property
    def smc_output_path(self) -> Path:
        """Path for SMC output file (with check results)."""
        return self.output_dir / "smc" / f"{self.model_name}_check.smc"
    
    def generate(self) -> str:
        """
        Generate autorun XML content.
        
        Returns:
            XML content as string
        """
        xml_content = f'''<?xml version="1.0" encoding="ISO-8859-1"?>
<batch name="Solibri_Autorun" default="root">
<!-- Solibri Autorun Configuration - Generated for {self.model_name} -->
<target name="root">

<!-- Open pre-configured SMC (contains model + rules + classifications) -->
<openmodel file="{self.smc_path}" />

<!-- Check model -->
<check/>

<!-- Add issue slides with description and snapshot zoomed to relevant component -->
<autocomment zoom="TRUE" />

<!-- Create a presentation from the slides -->
<createpresentation />

<!-- Create BCF Issue report from the Presentation view -->
<bcfreport file="{self.bcf_output_path}" version="2" />

<!-- Save model with issues -->
<savemodel file="{self.smc_output_path}" />

<exit />
</target>
</batch>
'''
        return xml_content
    
    def write(self, output_path: Optional[Path] = None) -> Path:
        """
        Generate and write autorun XML to file.
        
        Args:
            output_path: Where to write the file (defaults to acc/setup/autorun_setting.xml)
        
        Returns:
            Path to the written file
        """
        if output_path is None:
            output_path = self.setup_path / "autorun_setting.xml"
        
        # Ensure output directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "bcfzip").mkdir(exist_ok=True)
        (self.output_dir / "smc").mkdir(exist_ok=True)
        (self.output_dir / "issues").mkdir(exist_ok=True)
        
        xml_content = self.generate()
        
        output_path = Path(output_path)
        output_path.write_text(xml_content, encoding="utf-8")
        
        print(f"Generated autorun config for '{self.model_name}'")
        print(f"  SMC: {self.smc_path}")
        print(f"  Output: {self.output_dir}")
        
        return output_path


def generate_autorun(model_name: str) -> Path:
    """
    Convenience function to generate autorun config for a model.
    
    Args:
        model_name: Name of the model directory
    
    Returns:
        Path to the generated autorun_setting.xml
    """
    generator = AutorunGenerator(model_name)
    return generator.write()


if __name__ == "__main__":
    import sys
    
    model = sys.argv[1] if len(sys.argv) > 1 else "duplex"
    path = generate_autorun(model)
    print(f"\nWritten to: {path}")
