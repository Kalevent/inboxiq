# InboxIQ — Change Management Policy

**Owner:** Kalevent Ltd  
**Last reviewed:** May 2026  
**Next review:** May 2027  
**Version:** 1.0

---

## Purpose

This policy defines how code changes are reviewed, tested, and deployed to the InboxIQ production environment. It maps to SOC2 CC8.1 (change management controls).

---

## Scope

All changes to production application code, infrastructure configuration, database schema, and Kubernetes manifests.

---

## Change Process

### 1. Development

- All changes are made on a feature branch, never directly on `main`
- Branch naming convention: `<type>/<short-description>` (e.g. `feat/stripe-webhooks`, `fix/invoice-idor`)
- Developers run the test suite locally before opening a pull request:
  ```
  python -m pytest tests/ -v
  ```

### 2. Code Review

- All changes require a Pull Request (PR) on GitHub before merging to `main`
- PRs must be reviewed and approved before merge
- Branch protection on `main` enforces: no direct pushes, PR required
- Security-sensitive changes (auth, billing, data access) are flagged and reviewed with extra scrutiny

### 3. Automated Testing (CI)

- GitHub Actions runs on every PR:
  - Full test suite (`pytest`)
  - Lint and type checks
- PRs with failing CI cannot be merged

### 4. Deployment

- All production deployments are triggered by merging to `main` via GitHub Actions (`.github/workflows/inbox-ci.yml`)
- **No manual Docker builds or direct server deployments** — CI/CD is the only deployment path
- Deployment builds a new container image, pushes to ECR, and performs a rolling update on the EKS cluster (`kubectl rollout`)
- Rollback is performed via `kubectl rollout undo` if a deployment causes degradation

### 5. Database Migrations

- Schema changes use Flask-Migrate (Alembic) autogeneration — no hand-written SQL
- Migrations are reviewed in the PR before merge
- Production migrations run via a dedicated CI job with a manual approval gate ("Force run migrations" option)

### 6. Emergency Changes (Hotfixes)

- In the event of a P1 incident requiring an emergency fix, the same PR process applies but review can be expedited
- The change is documented in the incident post-mortem
- Post-incident, a normal PR is raised to add or update tests covering the fixed scenario

---

## Infrastructure Changes

- Kubernetes manifests live in `src/k8s/` and are version-controlled in the same repository
- AWS infrastructure changes (security groups, IAM, etc.) are performed via `aws cli` and documented in commit messages or incident reports
- Significant infrastructure changes are reviewed before being applied

---

## Audit Trail

Every merge to `main` is recorded in GitHub's commit history with author, timestamp, and PR reference. This provides a full audit trail of what changed, when, and who approved it.

---

## Responsibilities

| Role | Responsibility |
|---|---|
| Developer (Kofi Afor) | Writes code, opens PR, responds to review comments |
| Reviewer | Reviews PR for correctness, security, and test coverage |
| CI/CD pipeline | Enforces tests pass before deploy |
