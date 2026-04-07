# InboxIQ Repo Map

This repo has two separate operational surfaces:

- `infra/`: AWS infrastructure managed with Terraform.
- `src/`: application code, Kubernetes manifests, and deploy assets.

## Core app files

- `src/app.py`: Flask app factory and web entrypoint.
- `src/config.py`: environment-specific configuration.
- `src/manage.py`: Flask CLI entrypoint for migrations and admin tasks.
- `src/celery_inboxiq.py`: Celery app, queues, and worker/beat wiring.
- `src/Dockerfile.inboxiq`: production image build for web and worker containers.

## App code layout

- `src/api/v1/`: API routes.
- `src/automation/`: workflow engine and automation actions.
- `src/billing/`: billing services, jobs, and tasks.
- `src/content/`: content-generation task code.
- `src/dspy/`: DSPy training, inference, and content helpers.
- `src/templates/`: server-rendered HTML.
- `src/monitoring/`: Prometheus/OpenTelemetry instrumentation.

## Kubernetes manifests

- `src/k8s/inboxiq-deployment.yaml`: main web app deployment.
- `src/k8s/inboxiq-celery-*.yaml`: Celery workers and beat deployments.
- `src/k8s/redis.yaml`: in-cluster Redis.
- `src/k8s/priority-classes.yaml`: eviction order under pressure.
- `src/k8s/prometheus-values.yaml`: Helm values for Prometheus/Grafana.
- `src/k8s/grafana-ingress.yaml`: external Grafana ingress.
- `src/k8s/inboxiq-flask-servicemonitor.yaml`: Prometheus scrape config for the app.
- `src/k8s/celery-exporter.yaml`: Celery metrics exporter and ServiceMonitor.
- `src/k8s/storageclasses.yaml`: shared storage classes used by observability.
- `src/k8s/deploy-monitoring.sh`: exact manual deploy path for monitoring.

## CI/CD

- `.github/workflows/inbox-ci.yml`: builds the Docker image and deploys the app/Celery manifests.

Important: CI/CD does not install the monitoring stack. Monitoring is currently a separate manual path from `src/k8s/`.

## Infrastructure

- `infra/environments/production/`: live production root module.
- `infra/modules/eks/`: EKS cluster and node group.
- `infra/modules/networking/`: VPC and subnets.
- `infra/modules/iam/`: cluster and node IAM policies.
- `infra/modules/observability-storage/`: EFS for observability state.
