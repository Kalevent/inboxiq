# Deployment Steps (InboxIQ)

## Always run
```bash
# Configure kubectl for the cluster (run once per shell/session)
aws eks update-kubeconfig --name inboxiq-eks --region us-west-2

# Log in to ECR so docker can push
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 094985084741.dkr.ecr.us-west-2.amazonaws.com

# Build and push (amd64) with timestamp + git SHA tag
export REPO=094985084741.dkr.ecr.us-west-2.amazonaws.com/inboxiq
export TAG="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD)"
docker buildx build --platform linux/amd64 -f src/Dockerfile.inboxiq -t "${REPO}:${TAG}" --push .

# Roll out the new image to all workloads
kubectl set image deploy/inboxiq inboxiq="${REPO}:${TAG}" -n kaley
kubectl set image deploy/inboxiq-celery-inbox-worker inbox-worker="${REPO}:${TAG}" -n kaley
kubectl set image deploy/inboxiq-celery-inbox-beat   inbox-beat="${REPO}:${TAG}" -n kaley
kubectl set image deploy/inboxiq-celery-billing-worker billing-worker="${REPO}:${TAG}" -n kaley
kubectl set image deploy/inboxiq-celery-billing-beat   billing-beat="${REPO}:${TAG}"   -n kaley

# Restart pods to pick up new images (if needed)
# kubectl rollout restart deploy/inboxiq -n kaley
# kubectl rollout restart deploy/inboxiq-celery-inbox-worker -n kaley
# kubectl rollout restart deploy/inboxiq-celery-inbox-beat   -n kaley
# kubectl rollout restart deploy/inboxiq-celery-billing-worker -n kaley
# kubectl rollout restart deploy/inboxiq-celery-billing-beat   -n kaley

# Watch rollouts
kubectl rollout status deploy/inboxiq -n kaley
kubectl rollout status deploy/inboxiq-celery-inbox-worker -n kaley
kubectl rollout status deploy/inboxiq-celery-inbox-beat   -n kaley
kubectl rollout status deploy/inboxiq-celery-billing-worker -n kaley
kubectl rollout status deploy/inboxiq-celery-billing-beat   -n kaley

# Optional: Record change-cause for rollout history (useful for `kubectl rollout history`)
kubectl annotate deploy/inboxiq kubernetes.io/change-cause="deploy ${TAG}" -n kaley --overwrite
kubectl annotate deploy/inboxiq-celery-inbox-worker kubernetes.io/change-cause="deploy ${TAG}" -n kaley --overwrite
kubectl annotate deploy/inboxiq-celery-inbox-beat   kubernetes.io/change-cause="deploy ${TAG}" -n kaley --overwrite
kubectl annotate deploy/inboxiq-celery-billing-worker kubernetes.io/change-cause="deploy ${TAG}" -n kaley --overwrite
kubectl annotate deploy/inboxiq-celery-billing-beat   kubernetes.io/change-cause="deploy ${TAG}" -n kaley --overwrite
```

## Optional: Immediate rollback (last working revision)
Use if a new deployment crashes.
```bash
kubectl rollout undo deploy/inboxiq -n kaley
kubectl rollout undo deploy/inboxiq-celery-inbox-worker -n kaley
kubectl rollout undo deploy/inboxiq-celery-inbox-beat   -n kaley
kubectl rollout undo deploy/inboxiq-celery-billing-worker -n kaley
kubectl rollout undo deploy/inboxiq-celery-billing-beat   -n kaley


# Optional:If you need a specific known-good revision if deployement breaks the:
kubectl rollout history deploy/inboxiq -n kaley
kubectl rollout undo deploy/inboxiq -n kaley --to-revision=<REV_ID>
```

## As needed (DB migration job)
Use when schema changes are included.
```bash
# Set the job image to the current tag and keep small resources (already in job-migrate.yaml)
sed -i '' "s|094985084741.dkr.ecr.us-west-2.amazonaws.com/inboxiq:.*|${REPO}:${TAG}|" src/k8s/job-migrate.yaml

# Job inherits env from Kubernetes secrets/configmaps (no local .env needed)

kubectl delete job inboxiq-migrate -n kaley --ignore-not-found
kubectl apply -f src/k8s/job-migrate.yaml
kubectl logs -f job/inboxiq-migrate -n kaley
```

## DSPy training automation (Celery)
Enable per-tenant DSPy compilation without manual runs by turning on the Celery beat job.

Required env/config:
- `DSPY_TRAIN_AUTOMATION=1`
- `DSPY_TRAIN_SCHEDULE_HOUR=3` (UTC)
- `DSPY_TRAIN_SCHEDULE_MINUTE=0`
- `DSPY_TRAIN_LOOKBACK_DAYS=30`
- `DSPY_TRAIN_MIN_SAMPLES=20`
- `DSPY_TRAIN_LIMIT=200`
- `DSPY_TRAIN_MAX_ACCOUNTS=0` (0 = no cap)
- `DSPY_TRAIN_PROVIDERS=openai,anthropic,gemini` (optional; defaults to current `DSPY_PROVIDER`)
- `DSPY_TRAIN_MODEL_OPENAI=gpt-4o-mini` (optional overrides per provider)
- `DSPY_TRAIN_MODEL_ANTHROPIC=claude-3-5-sonnet`
- `DSPY_TRAIN_MODEL_GEMINI=gemini-1.5-pro`

Verification:
```bash
# Check Celery beat is scheduling the task
kubectl logs -n kaley deploy/inboxiq-celery-inbox-beat | rg "dspy_train_overrides"

# Check artifacts exist
kubectl exec -n kaley deploy/inboxiq -- ls -la /app/inboxiq/.dspy
```

## Seed published blog posts (cluster-only)
Use this to upsert all published fallback blog posts in production. Runs inside the cluster so it can reach RDS and use secret/config env.
```bash
IMAGE=$(kubectl get deploy/inboxiq -n kaley -o jsonpath='{.spec.template.spec.containers[0].image}')

cat >/tmp/blog-seed.yaml <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: blog-seed
  namespace: kaley
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: seed

        image: ${IMAGE}
        envFrom:
        - secretRef:
            name: inboxiq-env
        - configMapRef:
            name: inboxiq-config
        env:
        - name: APP_ENV
          value: production
        resources:
          requests:
            cpu: "50m"
            memory: "1Gi"
          limits:
            cpu: "250m"
            memory: "1.5Gi"
        command: ["/bin/sh","-c"]
        args:
        - |
          python - <<'PY'
          from datetime import datetime, timezone
          from src.app import create_app
          from src.extensions import db
          from src.models import BlogPost
          from src.blog_content import get_fallback_posts
          FIELDS = {
              "title","slug","status","funnel_stage","primary_keyword","secondary_keywords",
              "summary","excerpt","content_html","meta_description","canonical_url",
              "hero_image_url","hero_image_alt","word_count","read_time_minutes","internal_links",
              "published_at",
          }
          app = create_app()
          with app.app_context():
              posts = get_fallback_posts()
              filtered = []
              for post in posts:
                  if post.get("title") == "Release highlights":
                      continue  # skip internal/unpublished
                  if not post.get("slug"):
                      continue
                  filtered.append(post)
                  payload = {k: post.get(k) for k in FIELDS}
                  payload["published_at"] = payload.get("published_at") or datetime.now(timezone.utc)
                  payload["status"] = payload.get("status") or "published"
                  existing = BlogPost.query.filter_by(slug=post.get("slug")).first()
                  if existing:
                      for k, v in payload.items():
                          setattr(existing, k, v)
                  else:
                      db.session.add(BlogPost(**payload))
              db.session.commit()
              print(f"Upserted {len(filtered)} posts:", ", ".join(p.get("slug","?") for p in filtered))
          PY
EOF

kubectl delete job blog-seed -n kaley --ignore-not-found
kubectl apply -f /tmp/blog-seed.yaml
kubectl logs -f job/blog-seed -n kaley
```
Notes:
- Skips unpublished/internal “Release highlights” and any post without a slug.
- If the pod is OOM-killed (exit 137), increase memory in `/tmp/blog-seed.yaml` (e.g., requests 1.5Gi, limits 2Gi) and re-apply.
