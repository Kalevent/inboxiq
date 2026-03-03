#!/bin/bash
# Test script to verify security headers and app functionality

echo "🔒 Testing Security Headers & App Functionality"
echo "================================================"
echo ""

BASE_URL="https://127.0.0.1:8000"

# Function to test a page
test_page() {
    local path=$1
    local name=$2

    echo "📄 Testing: $name ($path)"

    # Check HTTP status
    status=$(curl -k -s -o /dev/null -w "%{http_code}" "$BASE_URL$path")
    if [ "$status" -eq 200 ] || [ "$status" -eq 302 ]; then
        echo "   ✅ Status: $status"
    else
        echo "   ❌ Status: $status (FAILED)"
        return 1
    fi

    # Check security headers
    headers=$(curl -k -I -s "$BASE_URL$path")

    if echo "$headers" | grep -q "Content-Security-Policy"; then
        echo "   ✅ CSP header present"
    else
        echo "   ❌ CSP header missing"
    fi

    if echo "$headers" | grep -q "X-XSS-Protection"; then
        echo "   ✅ X-XSS-Protection header present"
    else
        echo "   ⚠️  X-XSS-Protection header missing (NEW)"
    fi

    if echo "$headers" | grep -q "Permissions-Policy"; then
        echo "   ✅ Permissions-Policy header present"
    else
        echo "   ⚠️  Permissions-Policy header missing (NEW)"
    fi

    # Check for upgrade-insecure-requests in CSP
    if echo "$headers" | grep "Content-Security-Policy" | grep -q "upgrade-insecure-requests"; then
        echo "   ✅ upgrade-insecure-requests directive present"
    else
        echo "   ⚠️  upgrade-insecure-requests missing (NEW)"
    fi

    echo ""
}

# Test critical pages
echo "Testing critical pages..."
echo "------------------------"
test_page "/" "Homepage"
test_page "/login" "Login Page"
test_page "/settings/integrations?tab=integrations&view=webhooks" "Webhook Settings"
test_page "/docs" "Documentation"

echo ""
echo "📋 Full CSP Header:"
echo "-------------------"
curl -k -I -s "$BASE_URL/" | grep "Content-Security-Policy" | sed 's/Content-Security-Policy: //' | tr ';' '\n' | sed 's/^/  • /'

echo ""
echo "📋 All Security Headers:"
echo "------------------------"
curl -k -I -s "$BASE_URL/" | grep -E "Content-Security-Policy|X-XSS-Protection|X-Frame-Options|X-Content-Type-Options|Permissions-Policy|Referrer-Policy"

echo ""
echo "✅ Test complete! If all pages load and new headers are present, CSP is working correctly."
