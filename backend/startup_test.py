#!/usr/bin/env python3
"""
Startup diagnostic script to test imports and configuration
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("STARTUP DIAGNOSTIC TEST")
print("=" * 60)

# Test 1: Check Python version
print(f"\n✓ Python version: {sys.version}")

# Test 2: Check current directory
print(f"✓ Current directory: {os.getcwd()}")

# Test 3: Check .env file
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
print(f"✓ .env path: {env_path}")
print(f"✓ .env exists: {os.path.exists(env_path)}")

# Test 4: Import FastAPI
try:
    from fastapi import FastAPI
    print("✓ FastAPI import successful")
except ImportError as e:
    print(f"✗ FastAPI import failed: {e}")

# Test 5: Import dotenv
try:
    from dotenv import load_dotenv
    print("✓ python-dotenv import successful")
except ImportError as e:
    print(f"✗ python-dotenv import failed: {e}")

# Test 6: Import google generativeai
try:
    import google.generativeai as genai
    print("✓ google-generativeai import successful")
except ImportError as e:
    print(f"✗ google-generativeai import failed: {e}")

# Test 7: Import PIL
try:
    from PIL import Image
    print("✓ Pillow import successful")
except ImportError as e:
    print(f"✗ Pillow import failed: {e}")

# Test 8: Import uvicorn
try:
    import uvicorn
    print("✓ uvicorn import successful")
except ImportError as e:
    print(f"✗ uvicorn import failed: {e}")

# Test 9: Load and check environment variables
try:
    load_dotenv(env_path)
    api_key = os.getenv('GEMINI_API_KEY')
    if api_key:
        print(f"✓ GEMINI_API_KEY found (length: {len(api_key)})")
    else:
        print("⚠ GEMINI_API_KEY not set in .env")
except Exception as e:
    print(f"✗ Error loading .env: {e}")

# Test 10: Try importing main module
try:
    import main
    print("✓ main.py import successful")
except ImportError as e:
    print(f"✗ main.py import failed: {e}")
except Exception as e:
    print(f"✗ main.py execution error: {e}")

# Test 11: Try importing gemini_engine
try:
    import gemini_engine
    print("✓ gemini_engine.py import successful")
except ImportError as e:
    print(f"✗ gemini_engine.py import failed: {e}")
except Exception as e:
    print(f"✗ gemini_engine.py execution error: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
