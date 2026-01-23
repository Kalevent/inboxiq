"""
Compatibility wrapper that exposes the search tool over a simple line-delimited
JSON protocol ({"tool": "...", "arguments": {...}} per line). This bypasses the
MCP JSON-RPC handshake and is intended for lightweight callers like
PersistentMCPClient.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict

from src.mcp.search_mcp import _search_tool, _result_processor, _ctx


async def _run_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    args = payload.get("arguments") or {}
    query = args.get("query")
    context = args.get("context")
    max_results = args.get("max_results")
    if not query or not isinstance(query, str):
        return {"error": "query is required"}

    if max_results:
        _result_processor.max_results = max_results

    try:
        raw = await _search_tool.search(_ctx, query, context)
        processed = _result_processor.process_results(_ctx, raw, query)
        sources = {r.get("source") for r in processed if isinstance(r, dict) and r.get("source")}
        source_label = "mixed" if len(sources) > 1 else (sources.pop() if sources else "searxng")
        return {
            "query": query,
            "results": processed,
            "count": len(processed),
            "source": source_label,
            "context_applied": bool(context),
        }
    except Exception as exc:  # pragma: no cover - runtime safeguard
        return {"error": str(exc)}


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
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
        if tool != "search":
            sys.stdout.write(json.dumps({"error": "unknown tool"}) + "\n")
            sys.stdout.flush()
            continue

        result = loop.run_until_complete(_run_search(payload))
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
