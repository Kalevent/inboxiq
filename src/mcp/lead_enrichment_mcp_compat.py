"""
Compat shim for lead enrichment using line-delimited JSON protocol:
{"tool": "extract_contacts", "arguments": {"text": "...", "domain_hint": "..."}}
{"tool": "verify_email", "arguments": {"email": "..."}}
{"tool": "send_probe_email", "arguments": {"to_email": "..."}}

Implements minimal regex-based contact extraction and a basic verify stub.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}")


def extract_contacts(text: str, domain_hint: str | None = None) -> Dict[str, Any]:
    contacts: List[Dict[str, Any]] = []
    for match in EMAIL_REGEX.finditer(text or ""):
        contacts.append({"email": match.group(0), "domain": domain_hint or ""})
    return {"contacts": contacts}


def verify_email(email: str) -> Dict[str, Any]:
    # Stub: basic syntax check only.
    if EMAIL_REGEX.fullmatch(email or ""):
        return {"valid": True}
    return {"valid": False}


def send_probe_email(to_email: str) -> Dict[str, Any]:
    # Stub: pretend to send.
    return {"sent": True}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            sys.stdout.write(json.dumps({"error": "invalid json"}) + "\\n")
            sys.stdout.flush()
            continue

        tool = payload.get("tool")
        args = payload.get("arguments") or {}

        if tool == "extract_contacts":
            text = args.get("text", "")
            domain_hint = args.get("domain_hint")
            result = extract_contacts(text, domain_hint)
        elif tool == "verify_email":
            email = args.get("email", "")
            result = verify_email(email)
        elif tool == "send_probe_email":
            to_email = args.get("to_email", "")
            result = send_probe_email(to_email)
        else:
            result = {"error": "unknown tool"}

        sys.stdout.write(json.dumps(result) + "\\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
