from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Dict, Optional
from uuid import uuid4

from src.models.ai import AgentModel
from src.extensions import db


class AgentRegistry:
    """
    Minimal in-memory registry backed by the database for persistence.
    """

    def __init__(self) -> None:
        self._lock = RLock()

    def create(self, data: dict) -> AgentModel:
        with self._lock:
            agent = AgentModel(
                id=data.get("id") or str(uuid4()),
                name=data["name"],
                description=data.get("description"),
                status=data.get("status", "draft"),
                mcp_servers=data.get("mcp_servers") or [],
                capabilities=data.get("capabilities") or [],
                triggers=data.get("triggers") or [],
                human_review=data.get("human_review") or {},
                graph_node_ref=data.get("graph_node_ref"),
            )
            db.session.add(agent)
            db.session.commit()
            return agent

    def list(self, include_drafts: bool = True) -> list[AgentModel]:
        query = AgentModel.query
        if not include_drafts:
            query = query.filter(AgentModel.status == "published")
        return query.order_by(AgentModel.updated_at.desc()).all()

    def get(self, agent_id: str) -> Optional[AgentModel]:
        return AgentModel.query.get(agent_id)

    def publish(self, agent_id: str) -> Optional[AgentModel]:
        with self._lock:
            agent = AgentModel.query.get(agent_id)
            if not agent:
                return None
            agent.status = "published"
            agent.updated_at = datetime.utcnow()
            db.session.commit()
            return agent

    def update(self, agent_id: str, updates: dict) -> Optional[AgentModel]:
        with self._lock:
            agent = AgentModel.query.get(agent_id)
            if not agent:
                return None
            for key, value in updates.items():
                if hasattr(agent, key) and value is not None:
                    setattr(agent, key, value)
            agent.updated_at = datetime.utcnow()
            db.session.commit()
            return agent

    def delete(self, agent_id: str) -> bool:
        with self._lock:
            agent = AgentModel.query.get(agent_id)
            if not agent:
                return False
            db.session.delete(agent)
            db.session.commit()
            return True


def agent_to_dict(agent: AgentModel) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "status": agent.status,
        "mcp_servers": agent.mcp_servers or [],
        "capabilities": agent.capabilities or [],
        "triggers": agent.triggers or [],
        "human_review": agent.human_review or {},
        "graph_node_ref": agent.graph_node_ref,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }
