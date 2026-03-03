#!/bin/bash
# Rebuild Docker image with updated dependencies and deploy

set -e

echo "🔧 Building Docker image with updated dependencies..."

# Build and push to ECR
docker buildx build --platform linux/amd64 \
  -f src/Dockerfile.inboxiq \
  -t 094985084741.dkr.ecr.us-west-2.amazonaws.com/inboxiq:latest \
  --push .

echo "✅ Image built and pushed!"
echo ""
echo "📦 Deploying to Kubernetes..."

# Connect to cluster
aws eks update-kubeconfig --name inboxiq-eks --region us-west-2

# Update prod.env secret
kubectl delete secret inboxiq-env -n kaley || true
kubectl create secret generic inboxiq-env --from-env-file=src/prod.env -n kaley

# Deploy GSC credentials (if not already done)
kubectl delete secret gsc-credentials -n kaley 2>/dev/null || true
kubectl create secret generic gsc-credentials \
  --from-file=gsc-service-account.json=/Users/kofi/inboxiq/gsc-service-account.json \
  -n kaley

# Restart deployment to pick up new image and secrets
kubectl rollout restart deployment/inboxiq -n kaley

echo "✅ Deployment restarted!"
echo ""
echo "🔍 Watching rollout status..."
kubectl rollout status deployment/inboxiq -n kaley

echo ""
echo "✅ All done! New dependencies are now in production."
echo ""
echo "Verify GSC integration at: https://api.kalevent.com/api/v1/admin/blog-metrics"
