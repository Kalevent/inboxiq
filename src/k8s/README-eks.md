# InboxIQ EKS Deploy (Updated)

### 1) Cluster (eksctl)
```bash
eksctl create cluster -f src/infrastructure/eks-cluster.yaml
aws eks update-kubeconfig --name inboxiq-eks --region us-west-2
```

### 2) Secrets (from local .env)
Use apply to update without deleting:
```bash
cd src
kubectl create secret generic inboxiq-secrets \
  --namespace kaley \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```
Keep `src/k8s/inboxiq-config.yaml` for non-sensitive settings (hosts/ports). Real creds stay in the Secret.

### 3) Deploy core manifests
```bash
kubectl apply -f src/k8s/redis.yaml
kubectl apply -f src/k8s/inboxiq-config.yaml   # non-sensitive ConfigMap values
kubectl apply -f src/k8s/inboxiq-deployment.yaml
kubectl apply -f src/k8s/inboxiq-service.yaml
```

### 4) Run migrations against your DB
```bash
export FLASK_APP=src.manage:app
export DATABASE_URL=postgresql://<your-RDS-url>
flask db upgrade -d src/migrations
```

### 5) Smoke checks
```bash
kubectl port-forward deploy/inboxiq 8000:8000
curl http://localhost:8000/health
# If exposed via ingress/LB, set SMOKE_BASE_URL and run live smoke:
SMOKE_BASE_URL=https://<your-proxy> SMOKE_EMAIL=... SMOKE_PASSWORD=... pytest tests/test_smoke_live.py
```

### 6) Proxy/ingress
Point your ingress/ELB to the `inboxiq` service (ClusterIP). For local testing, use NodePort or port-forward.
