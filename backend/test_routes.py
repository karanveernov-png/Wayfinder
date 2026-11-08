#!/usr/bin/env python
"""Test script to check actual routes"""
import sys
sys.path.insert(0, '.')

from app.main import app

print("Routes:", file=sys.stderr)
for r in app.routes:
    if hasattr(r, 'path'):
        methods = getattr(r, 'methods', 'N/A')
        print(f'{r.path}: {methods}', file=sys.stderr)

# Also print to stdout
print("Routes:")
for r in app.routes:
    if hasattr(r, 'path'):
        methods = getattr(r, 'methods', 'N/A')
        print(f'{r.path}: {methods}')