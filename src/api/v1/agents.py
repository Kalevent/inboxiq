from __future__ import annotations

from flask import jsonify, request
import time
from flask_jwt_extended import jwt_required
from threading import Lock

from src.agents.registry import AgentRegistry, agent_to_dict
from src.models.ai import MCPServerCatalog
from src.extensions import db
from src.api.v1 import v1
from src.mcp.client import PersistentMCPClient
from src.ai.client import invoke_llm
from src.models.ai import AgentEvent

_registry_singleton: AgentRegistry | None = None
_mcp_client_pool: dict[tuple[str, ...], PersistentMCPClient] = {}
_mcp_pool_lock = Lock()


def _get_persistent_mcp_client(command: list[str]) -> PersistentMCPClient:
    """
    Reuse a single MCP subprocess per unique command to avoid spawn-per-call overhead.
    """
    key = tuple(command)
    with _mcp_pool_lock:
        client = _mcp_client_pool.get(key)
        if client is None:
            client = PersistentMCPClient(command)
            client.start()
            _mcp_client_pool[key] = client
        return client


def _registry() -> AgentRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = AgentRegistry()
    return _registry_singleton


def _select_mcp_server(mcp_servers: list, requested_label: str | None) -> tuple[dict | list | str, str | None]:
    """
    Choose an MCP server from the agent config. Supports explicit label selection.

    Returns (server_cfg, label_used).
    """
    if requested_label:
        for cfg in mcp_servers:
            label = cfg.get("label") if isinstance(cfg, dict) else None
            if label == requested_label:
                return cfg, label
        raise ValueError(f"Requested MCP server label '{requested_label}' not found.")

    if len(mcp_servers) == 1:
        cfg = mcp_servers[0]
        label = cfg.get("label") if isinstance(cfg, dict) else None
        return cfg, label

    raise ValueError("Multiple MCP servers configured; specify mcp_server_label in the payload.")


@v1.route("/agents", methods=["GET"])
@jwt_required(optional=True)
def list_agents():
    include_drafts = request.args.get("include_drafts", "true").lower() == "true"
    agents = _registry().list(include_drafts=include_drafts)
    return jsonify({"agents": [agent_to_dict(a) for a in agents]})


@v1.route("/agents", methods=["POST"])
@jwt_required(optional=True)
def create_agent():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    agent = _registry().create(data)
    return jsonify({"agent": agent_to_dict(agent)}), 201


@v1.route("/agents/<agent_id>", methods=["GET"])
@jwt_required(optional=True)
def get_agent(agent_id: str):
    agent = _registry().get(agent_id)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify({"agent": agent_to_dict(agent)})


@v1.route("/agents/<agent_id>/publish", methods=["POST"])
@jwt_required(optional=True)
def publish_agent(agent_id: str):
    agent = _registry().publish(agent_id)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify({"agent": agent_to_dict(agent)})


@v1.route("/agents/<agent_id>", methods=["PATCH"])
@jwt_required(optional=True)
def update_agent(agent_id: str):
    data = request.get_json() or {}
    agent = _registry().update(agent_id, data)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify({"agent": agent_to_dict(agent)})


@v1.route("/agents/<agent_id>", methods=["DELETE"])
@jwt_required(optional=True)
def delete_agent(agent_id: str):
    ok = _registry().delete(agent_id)
    if not ok:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify({"deleted": True})


@v1.route("/agents/<agent_id>/invoke", methods=["POST"])
@jwt_required(optional=True)
def invoke_agent(agent_id: str):
    """
    Invoke an agent tool. For MCP mode, if an agent has multiple MCP servers,
    set `mcp_server_label` in the payload to pick which server handles the tool.
    """
    agent = _registry().get(agent_id)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
    payload = request.get_json() or {}
    start_ts = time.perf_counter()

    def _log_agent_event(event: str, status: str | None = None, error: str | None = None):
        try:
            latency_ms = int((time.perf_counter() - start_ts) * 1000)
            evt = AgentEvent(
                agent_id=agent_id,
                agent_name=getattr(agent, "name", None),
                event=event,
                status=status,
                context={"payload_keys": list(payload.keys())},
                latency_ms=latency_ms if latency_ms >= 0 else None,
                error_message=(error or "")[:500] if error else None,
            )
            db.session.add(evt)
            db.session.commit()
        except Exception:
            db.session.rollback()

    # LLM path when requested
    if payload.get("use_llm") or payload.get("mode") == "llm" or payload.get("tool") == "llm":
        input_text = payload.get("input") or ""
        context = payload.get("context") or {}
        try:
            _log_agent_event("invoke", status="started")
            llm_result = invoke_llm(input_text, context)
            _log_agent_event("success", status="success")
            return jsonify({"agent_id": agent_id, "input": input_text, "llm_result": llm_result})
        except Exception as exc:
            _log_agent_event("error", status="error", error=str(exc))
            return jsonify({"error": f"LLM invocation failed: {exc}"}), 502

    mcp_servers = agent.mcp_servers or []
    if not mcp_servers:
        return jsonify({"error": "No MCP servers configured for this agent"}), 400
    try:
        server_cfg, server_label = _select_mcp_server(mcp_servers, payload.get("mcp_server_label"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    command = server_cfg if isinstance(server_cfg, list) else server_cfg.get("command") or server_cfg.get("cmd")
    if isinstance(command, str):
        command = [command]
    if not command:
        return jsonify({"error": "Invalid MCP server command"}), 400

    input_text = payload.get("input") or ""
    tool = payload.get("tool") or "triage_email_ticket"
    args = payload.get("arguments") or {}
    try:
        _log_agent_event("invoke", status="started")
        client = _get_persistent_mcp_client(command)
        result = client.invoke(tool, args)
    except Exception as exc:
        _log_agent_event("error", status="error", error=str(exc))
        return jsonify({"error": f"MCP invocation failed: {exc}"}), 502

    _log_agent_event("success", status="success")
    return jsonify({"agent_id": agent_id, "input": input_text, "result": result})


@v1.route("/agents/mcp/servers", methods=["GET"])
@jwt_required(optional=True)
def list_mcp_servers():
    servers = MCPServerCatalog.query.filter_by(enabled=True).order_by(MCPServerCatalog.label.asc()).all()
    return jsonify(
        {
            "servers": [
                {
                    "id": s.id,
                    "label": s.label,
                    "command": s.command,
                    "env": s.env,
                    "cwd": s.cwd,
                    "enabled": s.enabled,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in servers
            ]
        }
    )


@v1.route("/agents/mcp/servers", methods=["POST"])
@jwt_required(optional=True)
def upsert_mcp_server():
    data = request.get_json() or {}
    if not data.get("label") or not data.get("command"):
        return jsonify({"error": "label and command are required"}), 400
    existing = MCPServerCatalog.query.filter_by(label=data["label"]).first()
    if existing:
        existing.command = data.get("command")
        existing.env = data.get("env")
        existing.cwd = data.get("cwd")
        existing.enabled = bool(data.get("enabled", True))
        db.session.commit()
        server = existing
    else:
        server = MCPServerCatalog(
            label=data["label"],
            command=data["command"],
            env=data.get("env"),
            cwd=data.get("cwd"),
            enabled=bool(data.get("enabled", True)),
        )
        db.session.add(server)
        db.session.commit()
    return jsonify(
        {
            "server": {
                "id": server.id,
                "label": server.label,
                "command": server.command,
                "env": server.env,
                "cwd": server.cwd,
                "enabled": server.enabled,
                "created_at": server.created_at.isoformat() if server.created_at else None,
            }
        }
    )
