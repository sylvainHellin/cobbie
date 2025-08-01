#!/usr/bin/env python3
"""
Startup script for the IFC Answer Engine API server.
"""

import os
import sys
import uvicorn

# Add the project root directory to the Python path
project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.append(project_root)

if __name__ == "__main__":
    print("Starting IFC Answer Engine API server...")
    print("Server will be available at: http://127.0.0.1:8000")
    print("Interactive docs at: http://127.0.0.1:8000/docs")
    print("MLflow tracking enabled - check the 'API' experiment in MLflow UI")
    print("Press Ctrl+C to stop the server")

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
