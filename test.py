#!/usr/bin/env python3
"""Simple test to verify imports work."""

import sys

try:
    from index import create_cerebras_client
    print("✓ Import successful")
    sys.exit(0)
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)