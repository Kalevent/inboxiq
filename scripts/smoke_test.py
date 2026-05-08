"""
Post-deploy smoke test.

Hits every key public route and verifies no 5xx responses. Auth-required
routes are expected to return 302 (redirect to login) — that passes. Only
checks HTTP status codes; response bodies are never read or logged.

The route-checking logic lives in src/monitoring/smoke.py so this CI script
and the periodic Celery beat task (src/tasks/smoke.py) share one source of
truth — keeps the deploy-time check and the every-15-min check in lockstep.

Usage:
    python scripts/smoke_test.py https://kalevent.com

Exit code 0 = all clear, 1 = one or more failures.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.monitoring.smoke import check_routes


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/smoke_test.py <base_url>")
        print("Example: python scripts/smoke_test.py https://kalevent.com")
        return 1

    base_url = sys.argv[1].rstrip("/")
    print(f"Smoke test: {base_url}")
    print("-" * 60)

    results = check_routes(base_url=base_url)
    failures = []
    for r in results:
        status_str = str(r["status"]) if r["status"] is not None else "N/A"
        marker = "✅" if r["outcome"] == "pass" else "❌"
        print(f"{marker}  {status_str:>4}  {r['route']}")
        if r["outcome"] == "fail":
            failures.append((r["route"], status_str))
        time.sleep(0.2)

    print("-" * 60)
    if failures:
        print(f"\n❌ {len(failures)} route(s) failed:")
        for route, code in failures:
            print(f"   {code}  {route}")
        return 1

    print(f"\n✅ All {len(results)} routes passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
