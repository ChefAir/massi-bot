#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Massi-Bot — Webhook Endpoint Verification
# ═══════════════════════════════════════════════════════════════
#
# Tests that webhook endpoints are reachable and rejecting
# unsigned requests (which means HMAC verification is working).
#
# Usage: bash setup/test_webhooks.sh [domain]
#   e.g.: bash setup/test_webhooks.sh api.yourdomain.com
# ═══════════════════════════════════════════════════════════════

set -e

# Get domain from argument or .env
if [ -n "$1" ]; then
    DOMAIN="$1"
elif [ -f .env ]; then
    DOMAIN=$(grep ^DOMAIN= .env | cut -d= -f2 | tr -d '"' | tr -d "'")
fi

if [ -z "$DOMAIN" ]; then
    echo "ERROR: No domain specified."
    echo "Usage: bash setup/test_webhooks.sh api.yourdomain.com"
    exit 1
fi

BASE="https://$DOMAIN"
PASS=0
FAIL=0

check_endpoint() {
    local name="$1"
    local url="$2"
    local method="${3:-POST}"
    local expected_codes="$4"  # comma-separated acceptable HTTP codes

    printf "  %-40s " "$name"

    if [ "$method" = "GET" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
    else
        code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
            -H "Content-Type: application/json" \
            -d '{"test": true}' \
            "$url" 2>/dev/null)
    fi

    # Check if response code is in the expected list
    if echo "$expected_codes" | grep -q "$code"; then
        echo "OK (HTTP $code)"
        PASS=$((PASS + 1))
    else
        echo "UNEXPECTED (HTTP $code, expected: $expected_codes)"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "Testing Massi-Bot webhook endpoints at: $BASE"
echo "─────────────────────────────────────────────────────"
echo ""

echo "Fanvue Connector (port 8000):"
check_endpoint "POST /webhook/fanvue/ (no sig)" "$BASE/webhook/fanvue/" "POST" "401,403,422"
check_endpoint "GET  /oauth/start"               "$BASE/oauth/start"    "GET"  "200,302,307"
check_endpoint "GET  /health/fanvue"              "$BASE/health/fanvue"  "GET"  "200"
echo ""

echo "OnlyFans Connector (port 8001):"
check_endpoint "POST /webhook/of (no sig)"       "$BASE/webhook/of"     "POST" "401,403,422"
check_endpoint "GET  /health/of"                  "$BASE/health/of"      "GET"  "200"
echo ""

echo "─────────────────────────────────────────────────────"
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Some endpoints failed. Check that:"
    echo "  1. Docker containers are running: docker compose ps"
    echo "  2. Nginx is configured: sudo nginx -t"
    echo "  3. SSL certificate is installed: sudo certbot certificates"
    echo "  4. Firewall allows ports 80 and 443"
    exit 1
fi

echo "All endpoints responding correctly."
