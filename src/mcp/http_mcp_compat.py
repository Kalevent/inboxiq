"""
Lightweight compat HTTP fetcher using a line-delimited JSON protocol:
{"tool": "http_request", "arguments": {"url": "..."}}
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict

import requests


def http_request(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    try:
        resp = requests.get(url, timeout=timeout)
        return {
            "status": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp.text,
        }
    except Exception as exc:  # pragma: no cover - runtime safeguard
        return {"error": str(exc)}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            sys.stdout.write(json.dumps({"error": "invalid json"}) + "\n")
            sys.stdout.flush()
            continue

        tool = payload.get("tool")
        args = payload.get("arguments") or {}
        if tool != "http_request":
            sys.stdout.write(json.dumps({"error": "unknown tool"}) + "\n")
            sys.stdout.flush()
            continue

        url = args.get("url")
        if not url or not isinstance(url, str):
            sys.stdout.write(json.dumps({"error": "url is required"}) + "\n")
            sys.stdout.flush()
            continue

        result = http_request(url)
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
