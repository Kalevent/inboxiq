"""
Minimal MCP client helper to invoke tools against a configured MCP server command.
"""
from __future__ import annotations

import subprocess
import json
import selectors
import sys
from threading import Lock
from typing import Any, List, Dict


class PersistentMCPClient:
    """
    Lightweight long-lived MCP client that keeps a single subprocess alive
    and reuses it for multiple tool calls (avoids process spawn per call).
    Not thread-safe across processes; guarded with a lock for reentrancy.
    """

    def __init__(self, command: List[str], timeout: float = 30.0, line_protocol: bool | None = None, server_label: str | None = None):
        self.command = command
        self.timeout = timeout
        self.proc: subprocess.Popen[str] | None = None
        self.sel = selectors.DefaultSelector()
        self._lock = Lock()
        self._req_id = 0
        # Use line-delimited protocol for compat shims (e.g., search_mcp_compat); otherwise JSON-RPC.
        if line_protocol is None:
            joined = " ".join(command)
            self.line_protocol = "compat" in joined
        else:
            self.line_protocol = line_protocol
        # Optional label used for prometheus metrics; falls back to last command segment.
        if server_label:
            self.server_label = server_label
        else:
            try:
                last = command[-1] if command else "unknown"
                # Strip path + extension to keep label cardinality low (e.g., "lead_discovery_mcp")
                import os as _os
                base = _os.path.basename(last)
                self.server_label = base.rsplit(".", 1)[0] or base or "unknown"
            except Exception:
                self.server_label = "unknown"

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def start(self):
        if self.proc is not None:
            return
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
        if self.proc.stdout:
            self.sel.register(self.proc.stdout, selectors.EVENT_READ)
        if self.proc.stderr:
            self.sel.register(self.proc.stderr, selectors.EVENT_READ)

    def close(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass
            try:
                if self.proc.stdout:
                    self.sel.unregister(self.proc.stdout)
            except Exception:
                pass
            self.proc = None

    def invoke(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Time every invocation against the prometheus histogram. Import locally
        # so that test environments without prometheus_client don't crash; failures
        # to record metrics are silent (telemetry must not break the call path).
        try:
            from src.monitoring.metrics import mcp_tool_call_duration
            timer_cm = mcp_tool_call_duration.labels(
                server_label=getattr(self, "server_label", "unknown"),
                tool=tool,
            ).time()
        except Exception:
            timer_cm = None

        if timer_cm is None:
            return self._invoke_inner(tool, arguments)
        with timer_cm:
            return self._invoke_inner(tool, arguments)

    def _invoke_inner(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if self.proc is None:
            self.start()
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("MCP process is not available")

        if self.line_protocol:
            # Line-delimited JSON payload understood by our MCP shims (compat).
            payload = json.dumps({"tool": tool, "arguments": arguments}) + "\n"
        else:
            # JSON-RPC 2.0 request expected by FastMCP (call_tool).
            self._req_id += 1
            req_id = self._req_id
            payload = json.dumps(
                {
                    "id": req_id,
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments},
                }
            ) + "\n"
        with self._lock:
            try:
                self.proc.stdin.write(payload)
                self.proc.stdin.flush()
            except Exception as exc:
                raise RuntimeError(f"MCP write failed: {exc}") from exc

            # Read response; for JSON-RPC match id, for line protocol just read one line.
            while True:
                events = self.sel.select(self.timeout)
                if not events:
                    if self.proc.poll() not in (None, 0):
                        stderr_data = ""
                        if self.proc.stderr:
                            try:
                                stderr_data = self.proc.stderr.read()
                            except Exception:
                                pass
                        raise RuntimeError(f"MCP response timed out; proc exit={self.proc.poll()}, stderr={stderr_data}")
                    raise TimeoutError(f"MCP response timed out after {self.timeout}s")

                line = ""
                for key, _ in events:
                    if key.fileobj is self.proc.stdout:
                        try:
                            line = self.proc.stdout.readline()
                        except Exception as exc:
                            raise RuntimeError(f"MCP read failed: {exc}") from exc
                        break
                    if key.fileobj is self.proc.stderr:
                        try:
                            stderr_line = self.proc.stderr.readline()
                        except Exception:
                            stderr_line = ""
                        raise RuntimeError(f"MCP stderr: {stderr_line}")

                if not line:
                    raise RuntimeError("MCP returned no stdout/stderr data")

                if self.line_protocol:
                    try:
                        return json.loads(line.strip() or "{}")
                    except Exception:
                        return {"raw": line.strip()}

                # JSON-RPC path: match id
                try:
                    msg = json.loads(line.strip() or "{}")
                except Exception:
                    return {"raw": line.strip()}

                if msg.get("id") != req_id:
                    continue  # notification or other response

                if "error" in msg:
                    return {"error": msg.get("error"), "raw": msg}
                return msg.get("result") or msg

        if self.proc.poll() not in (None, 0):
            stderr_data = ""
            if self.proc.stderr:
                try:
                    stderr_data = self.proc.stderr.read()
                except Exception:
                    pass
            raise RuntimeError(f"MCP process exited ({self.proc.returncode}); stderr: {stderr_data}")

        try:
            return json.loads(line.strip() or "{}")
        except Exception:
            return {"raw": line.strip()}
