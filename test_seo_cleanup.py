#!/usr/bin/env python3
"""
Test SEO cleanup patterns to verify they only match old URLs.

Run this BEFORE deploying to make sure current URLs aren't affected.
"""
import sys
sys.path.insert(0, 'src')

from src.seo_cleanup import is_old_url

# Test old URLs (should return True - will get 410)
old_urls = [
    '/en-gb/contacts/contact',
    '/es-es/set_locale/?lc=es-es',
    '/en-us/auth/reset_password_request',
    '/fr-fr/crm/lead/contact_sales',
    '/home/',
    '/careers/?lc=en-gb',
    '/crm/leads',
    '/set_locale/?lc=en-gb',
]

# Test current URLs (should return False - will work normally)
current_urls = [
    '/',
    '/contact',
    '/auth/reset-password',
    '/auth/login',
    '/blog',
    '/blog/my-post',
    '/api/v1/leads',
    '/admin',
    '/funnel/dashboard',
    '/publishing',
]

print("🧪 Testing SEO cleanup patterns...\n")

print("=" * 60)
print("OLD URLs (should be blocked with 410 Gone):")
print("=" * 60)
for url in old_urls:
    result = is_old_url(url)
    status = "✅ WILL BLOCK" if result else "❌ WON'T BLOCK (check pattern!)"
    print(f"{status:20} {url}")

print("\n" + "=" * 60)
print("CURRENT URLs (should work normally):")
print("=" * 60)
for url in current_urls:
    result = is_old_url(url)
    status = "❌ WILL BLOCK (DANGER!)" if result else "✅ SAFE"
    print(f"{status:20} {url}")

print("\n" + "=" * 60)
print("Summary:")
print("=" * 60)

old_blocked = sum(1 for url in old_urls if is_old_url(url))
current_safe = sum(1 for url in current_urls if not is_old_url(url))

print(f"Old URLs blocked: {old_blocked}/{len(old_urls)}")
print(f"Current URLs safe: {current_safe}/{len(current_urls)}")

if old_blocked == len(old_urls) and current_safe == len(current_urls):
    print("\n✅ ALL TESTS PASSED! Safe to deploy.")
    sys.exit(0)
else:
    print("\n⚠️  TESTS FAILED! Review patterns before deploying.")
    sys.exit(1)
