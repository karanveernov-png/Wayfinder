#!/usr/bin/env python
"""Quick JWT validation test"""
import sys
sys.path.insert(0, '.')

from jose import jwt
from app.core.config import get_settings

settings = get_settings()
print(f"JWT Secret configured: {bool(settings.SUPABASE_JWT_SECRET)}")
print(f"JWT Secret length: {len(settings.SUPABASE_JWT_SECRET or '')}")

# Test signing a mock token
mock_token = jwt.encode(
    {"sub": "test-user-id", "role": "authenticated", "exp": 9999999999},
    settings.SUPABASE_JWT_SECRET,
    algorithm="HS256"
)
print(f"\nMock token generated: {mock_token[:50]}...")

# Verify it can be decoded
try:
    payload = jwt.decode(
        mock_token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated"
    )
    print(f"✅ JWT validation successful! User ID: {payload['sub']}")
except Exception as e:
    print(f"❌ JWT validation failed: {e}")

print("\nTo fix 'Invalid token' error:")
print("1. Go to https://supabase.com/dashboard/project/wxmvhqjxrseamshacynj/settings/api")
print("2. Scroll to 'JWT Settings' section")
print("3. Copy the 'JWT Secret' value (NOT the anon/service role key)")
print("4. Paste it into backend/.env as SUPABASE_JWT_SECRET=<your-secret>")
print("5. Restart the backend: taskkill /F /IM uvicorn.exe && start backend server again")
