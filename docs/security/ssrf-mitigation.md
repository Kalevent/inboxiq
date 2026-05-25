# SSRF Mitigation: User-Provided and API-Returned URLs

## What is SSRF?

Server-Side Request Forgery (SSRF) occurs when an attacker tricks the server
into making HTTP requests to unintended destinations — most dangerously to
internal services (AWS metadata at 169.254.169.254, Redis, RDS, other pods).

In InboxIQ, URLs enter the system from several sources:

| Source | Example | Risk level |
|--------|---------|------------|
| Lead `linkedin_url` stored in DB | `https://linkedin.com/in/...` | High — user-entered |
| SearXNG search result URLs | `https://acme.com` | High — third-party |
| OpenAI DALL-E API response | `https://oaidallee...blob.core.windows.net/...` | Low — trusted API |
| HeyGen render_url | `https://...heygen.com/...` | Low — trusted API |
| Direct user input (booking URLs, webhooks) | varies | High |

---

## Defence Layer 1 — Application Code (`_safe_external_url`)

**Location:** `src/mcp/enrichment_v2_mcp.py`

Every URL that the application fetches externally must pass through
`_safe_external_url(url)` before any HTTP request is made.

### Checks performed (in order)

1. **Scheme** — only `http` and `https` are permitted. Blocks `file://`,
   `ftp://`, `gopher://`, `dict://`, etc.

2. **Port** — if an explicit port is present, only 80 and 443 are allowed.
   Blocks attempts to reach `:6379` (Redis), `:5432` (Postgres), `:22` (SSH),
   `:3306` (MySQL), etc.

3. **String pattern (fast path)** — rejects obvious private hostnames
   (`localhost`, `127.x`, `10.x`, `192.168.x`, `172.16–31.x`, `169.254.x`)
   without a DNS lookup.

4. **DNS resolution** — resolves the hostname and checks every returned IP
   against all private/reserved ranges (IPv4 and IPv6). This catches
   `evil.com → 10.0.0.1` bypass attacks where the string looks public but
   resolves to a private address.

### Redirect re-validation (`_safe_get`)

Use `_safe_get(url)` instead of `requests.get(url)` for any fetch that may
follow redirects. It re-runs `_safe_external_url` on every `Location` header
before following the hop, preventing `evil.com/redirect → 127.0.0.1` attacks.

### Usage pattern

```python
from src.mcp.enrichment_v2_mcp import _safe_external_url, _safe_get

# Validate only (Playwright, or when you pass the URL to another library)
validated_url = _safe_external_url(user_supplied_url)

# Validate + fetch with redirect protection (requests-based fetches)
response = _safe_get(user_supplied_url, timeout=30)
```

### Where it is applied

| File | Location | URL source |
|------|----------|------------|
| `src/mcp/enrichment_v2_mcp.py` | `find_email_via_playwright()` | DB lead URL |
| `src/mcp/enrichment_v2_mcp.py` | `find_email_via_search()` | SearXNG result |
| `src/funnel/tasks.py` | `_real_website_url()` | DB lead URL |
| `src/content/tasks.py` | before DALL-E image download | OpenAI API response |
| `src/tasks/youtube.py` | before DALL-E frame download | OpenAI API response |
| `src/mcp/youtube_mcp.py` | before HeyGen video download | HeyGen API response |

---

## Defence Layer 2 — Kubernetes NetworkPolicy

**Location:** `src/k8s/network-policy-egress.yaml`

Even if `_safe_external_url` is bypassed (e.g. a DNS rebinding attack that
changes the record after validation but before the request), the CNI plugin
drops the packet at the kernel level.

The policy:
- Allows DNS (port 53)
- Allows HTTP/HTTPS (80, 443) to public IPs only — explicitly blocks all
  RFC-1918, 169.254.x.x, and loopback ranges
- Allows intra-namespace traffic to Redis (6379) and RDS (5432) via cluster DNS

**Apply once per cluster:**
```bash
kubectl apply -f src/k8s/network-policy-egress.yaml
```

**Verify it is active:**
```bash
kubectl get networkpolicy -n kaley
```

---

## Why Two Layers?

Application-layer validation alone can be defeated by DNS rebinding: the
hostname resolves to a public IP at validation time, then switches to a
private IP for the actual TCP connection. The network policy closes this
window because it operates independently of DNS.

Neither layer alone is sufficient. Both must hold for an attack to succeed.

---

## Adding a New External Fetch

If you add a new code path that makes an HTTP request to a URL that is:
- stored in the database
- returned by a third-party API
- submitted by a user

you **must** call `_safe_external_url(url)` before the request, or use
`_safe_get(url)` as the fetch primitive. PRs that skip this will be flagged
in security review.

The only exceptions are hardcoded URLs to known trusted services
(e.g. `https://api.hunter.io/...`, `https://api.openai.com/...`) where the
host is not derived from any external input.
