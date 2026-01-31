# Project Instructions for Claude

## Project Overview
This is a Flask-based monolith running in Kubernetes.
The app contains AI agents, MCP tools, workflow automation, analytics, and automated prompt optimization and reasoning pipelines implemented using the DSPy library.

## Tech Stack
- Python 3.11
- Flask (MVC)
- SQLAlchemy
- Celery for background tasks
- Kubernetes (no Docker Compose)
- UUIDs string preferred for primary identifiers

## Coding Rules
- Prefer Flask blueprints
- Do not introduce new services unless asked
- Keep changes minimal and explicit
- Avoid over-engineering
- Ask before refactoring existing models

## AI Behavior
- Be pragmatic and opinionated
- Default to production-ready patterns
- Explain tradeoffs briefly
- No unnecessary abstractions
- Always consider security vulnerabilities and follow secure-by-default implementation practices
