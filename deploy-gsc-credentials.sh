#!/bin/bash
# Deploy GSC credentials to Kubernetes

set -e

echo "📦 Creating GSC credentials secret in Kubernetes..."

# Make sure you're connected to the right cluster
aws eks update-kubeconfig --name inboxiq-eks --region us-west-2

# Delete old secret if exists
kubectl delete secret gsc-credentials -n kaley 2>/dev/null || true

# Create new secret from the JSON file
kubectl create secret generic gsc-credentials \
  --from-file=gsc-service-account.json=/Users/kofi/inboxiq/gsc-service-account.json \
  -n kaley

echo "✅ GSC credentials secret created!"
echo ""
echo "Next steps:"
echo "1. Redeploy your app for the volume mount to take effect"
echo "2. Add the service account email to Google Search Console"
echo "   Email: inboxiq-gsc-reader@inboxiq-480422.iam.gserviceaccount.com"
