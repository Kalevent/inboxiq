"""
Celery orchestration for lead sourcing via MCP servers:
- search (search-mcp)
- fetch (http-mcp)
- extract/verify/probe (lead-enrichment-mcp)
- upsert (sql-mcp)
"""
from __future__ import annotations

from threading import Lock
from typing import Any, Dict, List
from urllib.parse import urlparse
from uuid import uuid4

from datetime import datetime, timedelta

from sqlalchemy import text

from celery import shared_task
from src.extensions import db
from src.models import AgentModel, Lead
from src.mcp_client import PersistentMCPClient

_pool_lock = Lock()
_mcp_pool: Dict[tuple[str, ...], PersistentMCPClient] = {}


def _get_client(command: List[str]) -> PersistentMCPClient:
    key = tuple(command)
    with _pool_lock:
        client = _mcp_pool.get(key)
        if client is None:
            client = PersistentMCPClient(command)
            client.start()
            _mcp_pool[key] = client
        return client


def _command_by_label(agent: AgentModel, label: str) -> List[str] | None:
    for cfg in agent.mcp_servers or []:
        if isinstance(cfg, dict) and cfg.get("label") == label:
            cmd = cfg.get("command") or cfg.get("cmd")
            if isinstance(cmd, str):
                return [cmd]
            return cmd
    return None


def _sql_escape(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("'", "''")


@shared_task(name="leads.sourcing_job", bind=True, max_retries=0, queue="leads")
def sourcing_job(
    self,
    agent_id: str,
    queries: List[str],
    max_results_per_query: int = 5,
    send_probe: bool = False,
) -> Dict[str, Any]:
    agent = AgentModel.query.get(agent_id)
    if not agent:
        return {"status": "error", "error": f"Agent {agent_id} not found"}

    label_cmds = {}
    for lbl in ("search-mcp", "http-mcp", "lead-enrichment-mcp", "sql-mcp"):
        cmd = _command_by_label(agent, lbl)
        if not cmd:
            return {"status": "error", "error": f"MCP server '{lbl}' not configured on agent"}
        # Prefer compat shims to avoid FastMCP stream errors.
        # Force compat shims to avoid FastMCP errors in production.
        if lbl == "search-mcp":
            label_cmds[lbl] = ["python", "-m", "src.mcp.search_mcp_compat"]
        elif lbl == "http-mcp":
            label_cmds[lbl] = ["python", "-m", "src.mcp.http_mcp_compat"]
        elif lbl == "lead-enrichment-mcp":
            label_cmds[lbl] = ["python", "-m", "src.mcp.lead_enrichment_mcp_compat"]
        else:
            label_cmds[lbl] = cmd if isinstance(cmd, list) else [cmd]

    def invoke(label: str, tool: str, args: Dict[str, Any]) -> Any:
        client = _get_client(label_cmds[label])
        return client.invoke(tool, args)

    inserted = 0
    attempted = 0
    kept = []
    debug_urls: list[str] = []
    debug_counts = {
        "urls_seen": 0,
        "contacts_extracted": 0,
        "contacts_no_email": 0,
        "verify_failed": 0,
    }

    for query in queries or []:
        search_res = invoke("search-mcp", "search", {"query": query, "max_results": max_results_per_query})
        results = (search_res or {}).get("results") or []
        debug_counts["urls_seen"] += len(results)
        for r in results:
            url = r.get("url")
            if not url:
                continue
            fetch_res = invoke("http-mcp", "http_request", {"url": url})
            body = (fetch_res or {}).get("body") or ""
            if not body:
                continue
            domain_hint = urlparse(url).netloc
            debug_urls.append(url)
            extracted = invoke(
                "lead-enrichment-mcp",
                "extract_contacts",
                {"text": body, "domain_hint": domain_hint},
            )
            contacts = (extracted or {}).get("contacts") or []
            debug_counts["contacts_extracted"] += len(contacts)
            for c in contacts:
                email = c.get("email")
                if not email:
                    debug_counts["contacts_no_email"] += 1
                    continue
                verify = invoke("lead-enrichment-mcp", "verify_email", {"email": email})
                if not verify or not verify.get("valid"):
                    debug_counts["verify_failed"] += 1
                    continue
                if send_probe:
                    probe = invoke("lead-enrichment-mcp", "send_probe_email", {"to_email": email})
                    if not probe or not probe.get("sent"):
                        continue

                attempted += 1
                lead_id = str(uuid4())
                name = c.get("name") or c.get("title") or "Lead"
                title = c.get("title") or ""
                company = domain_hint or ""
                notes = f"title={title}; source_url={url}"
                sql = (
                    "insert into leads (id, name, email, company_name, source, status, score, notes) "
                    f"values ('{_sql_escape(lead_id)}','{_sql_escape(name)}','{_sql_escape(email)}',"
                    f"'{_sql_escape(company)}','lead_sourcing_agent','New Lead',0,'{_sql_escape(notes)}') "
                    "on conflict (id) do nothing"
                )
                invoke("sql-mcp", "execute", {"sql": sql, "requires_human": True})
                inserted += 1
                kept.append({"email": email, "name": name, "title": title, "source_url": url})

    return {
        "status": "ok",
        "inserted": inserted,
        "attempted": attempted,
        "kept": kept,
        "debug": {
            "queries": queries,
            "urls_seen": debug_counts["urls_seen"],
            "contacts_extracted": debug_counts["contacts_extracted"],
            "contacts_no_email": debug_counts["contacts_no_email"],
            "verify_failed": debug_counts["verify_failed"],
            "urls_sample": debug_urls[:10],
        },
    }


@shared_task(name="leads.sync_recipients", bind=True, max_retries=0, queue="leads")
def sync_recipients(
    self,
    min_score: int = 0,
    status: str = "New Lead",
    max_age_hours: int | None = None,
    topics: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Push eligible leads into newsletter recipients (deduped on email).
    """
    topics = topics or ["newsletter"]
    since = None
    if max_age_hours:
        since = datetime.utcnow() - timedelta(hours=max_age_hours)

    q = Lead.query.filter(Lead.status == status)
    if min_score:
        q = q.filter(Lead.score >= min_score)
    if since:
        q = q.filter(Lead.created_at >= since)

    leads = q.all()
    inserted = 0
    for lead in leads:
        email = (lead.email or "").strip()
        if not email:
            continue
        uid = str(uuid4())
        name = lead.name or lead.company_name or "Lead"
        topics_sql = "{" + ",".join([t.replace(",", "") for t in topics]) + "}"
        stmt = text(
            """
            INSERT INTO recipients (uid, email, name, is_unsubscribed, topics, suppressed, created_at)
            VALUES (:uid, :email, :name, false, :topics, false, NOW())
            ON CONFLICT (email) DO NOTHING
            """
        )
        try:
            db.session.execute(stmt, {"uid": uid, "email": email, "name": name, "topics": topics_sql})
            db.session.commit()
            inserted += 1
        except Exception:
            db.session.rollback()
            continue

    return {"status": "ok", "inserted": inserted, "candidates": len(leads)}
