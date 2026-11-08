#!/usr/bin/env python
"""Test Supabase connection and saved_journeys table"""
import sys
sys.path.insert(0, '.')

from supabase import create_client
from app.core.config import get_settings

settings = get_settings()
print(f"Supabase URL: {settings.SUPABASE_URL}")
print(f"Service Role Key configured: {bool(settings.SUPABASE_SERVICE_ROLE_KEY)}")
print(f"JWT Secret configured: {bool(settings.SUPABASE_JWT_SECRET)}")

client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

# Test 1: Check if saved_journeys table exists
try:
    result = client.table('saved_journeys').select('*').limit(1).execute()
    print(f"\n✅ Supabase connection OK - table accessible")
    print(f"Rows in saved_journeys: {len(result.data)}")
except Exception as e:
    error_msg = str(e)
    if 'relation "saved_journeys" does not exist' in error_msg or '44P01' in error_msg:
        print(f"\n❌ Table 'saved_journeys' does not exist!")
        print("Run backend/supabase/schema.sql in Supabase SQL Editor first.")
    else:
        print(f"\n❌ Error accessing table: {error_msg}")

# Test 2: Verify JWT secret matches
print("\n--- JWT Configuration ---")
print(f"JWT Secret length: {len(settings.SUPABASE_JWT_SECRET or '')} chars")
print(f"Starts with expected pattern: {settings.SUPABASE_JWT_SECRET.startswith('P5tB') if settings.SUPABASE_JWT_SECRET else False}")
