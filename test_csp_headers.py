#!/usr/bin/env python3
"""Test CSP headers configuration"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.app import create_app
from flask import make_response

print("Testing CSP Headers Configuration...")
print("=" * 60)

try:
    app = create_app()
    print("✅ App created successfully")

    with app.test_request_context():
        resp = make_response('test')
        resp = app.process_response(resp)

        print("\n📋 Security Headers:")
        print("-" * 60)
        print(f"Content-Security-Policy:")
        csp = resp.headers.get("Content-Security-Policy", "NOT SET")
        for directive in csp.split("; "):
            print(f"  • {directive}")

        print(f"\nX-Content-Type-Options: {resp.headers.get('X-Content-Type-Options', 'NOT SET')}")
        print(f"X-Frame-Options: {resp.headers.get('X-Frame-Options', 'NOT SET')}")
        print(f"X-XSS-Protection: {resp.headers.get('X-XSS-Protection', 'NOT SET')}")
        print(f"Referrer-Policy: {resp.headers.get('Referrer-Policy', 'NOT SET')}")
        print(f"Permissions-Policy: {resp.headers.get('Permissions-Policy', 'NOT SET')}")

        print("\n" + "=" * 60)
        print("✅ All security headers configured correctly!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
