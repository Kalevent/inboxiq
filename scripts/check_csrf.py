#!/usr/bin/env python3
"""Check all HTML templates for POST forms missing CSRF tokens"""
import os
import re

def check_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if file has POST forms
    has_post_form = re.search(r'method=["\']POST["\']', content, re.IGNORECASE)
    has_csrf = re.search(r'csrf_token', content, re.IGNORECASE)

    if has_post_form and not has_csrf:
        return True
    return False

def main():
    templates_dir = 'src/templates'
    missing_csrf = []

    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                filepath = os.path.join(root, file)
                if check_file(filepath):
                    missing_csrf.append(filepath)

    if missing_csrf:
        print("❌ Files with POST forms missing CSRF tokens:")
        for f in sorted(missing_csrf):
            print(f"  - {f}")
        print(f"\nTotal: {len(missing_csrf)} files")
    else:
        print("✅ All POST forms have CSRF tokens!")

if __name__ == '__main__':
    main()
