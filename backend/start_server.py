#!/usr/bin/env python
"""
Server startup wrapper for Lifestyle Lens Dashboard
This script starts the FastAPI server with proper module path setup
"""
import sys
import os

# Add current directory to path so 'main' module can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        'main:app',
        host='0.0.0.0',
        port=8000,
        reload=True,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))]
    )
