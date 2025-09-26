"""
Site customization for the ifcAnswerEngineV3 project.
This file is automatically imported by Python and sets up the environment.
"""

import os
import sys
from pathlib import Path


def setup_project_environment():
    """Setup project environment automatically when Python starts."""
    try:
        # Only run if we're in the project directory
        current_dir = Path.cwd()
        project_markers = ["pyproject.toml", "uv.lock"]

        # Check if we're in the project root or a subdirectory
        search_dir = current_dir
        project_root = None

        # Search up the directory tree for project markers
        for _ in range(5):  # Limit search depth
            if any((search_dir / marker).exists() for marker in project_markers):
                project_root = search_dir
                break
            parent = search_dir.parent
            if parent == search_dir:  # Reached filesystem root
                break
            search_dir = parent

        if project_root:
            # Try to load dotenv if available
            try:
                from dotenv import load_dotenv, find_dotenv

                # Load .env from project root
                env_file = project_root / ".env"
                if env_file.exists():
                    load_dotenv(env_file)
                else:
                    load_dotenv(find_dotenv())
            except ImportError:
                pass

            # Get ROOT_PATH from environment
            root_path = os.getenv("ROOT_PATH")

            if root_path:
                # Convert to absolute path
                root_path = os.path.abspath(root_path)

                # Add to sys.path if not already present
                if root_path not in sys.path:
                    sys.path.insert(0, root_path)

    except Exception:
        # Silently fail to avoid breaking Python startup
        pass


# Execute setup
setup_project_environment()

