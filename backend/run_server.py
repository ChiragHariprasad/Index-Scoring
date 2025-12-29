#!/usr/bin/env python3
"""
Run the FastAPI server directly using uvicorn programmatically
This avoids module import issues with uvicorn CLI
"""

import uvicorn
import os
import sys

# Set up environment
os.environ.setdefault("PYTHONUNBUFFERED", "1")

if __name__ == "__main__":
    # Run uvicorn with the app
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True
    )
