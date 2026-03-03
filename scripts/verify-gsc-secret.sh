#!/bin/bash
# Verify GSC secret exists in Kubernetes

echo "🔍 Checking for GSC credentials secret in Kubernetes..."
echo ""

# Connect to cluster
aws eks update-kubeconfig --name inboxiq-eks --region us-west-2 2>/dev/null

# Check if secret exists
if kubectl get secret gsc-credentials -n kaley &>/dev/null; then
    echo "✅ Secret 'gsc-credentials' exists in namespace 'kaley'"
    echo ""
    echo "Secret details:"
    kubectl describe secret gsc-credentials -n kaley
    echo ""
    echo "📊 Secret size:"
    kubectl get secret gsc-credentials -n kaley -o jsonpath='{.data.gsc-service-account\.json}' | base64 -d | wc -c | awk '{print $1 " bytes"}'
else
    echo "❌ Secret 'gsc-credentials' NOT FOUND in namespace 'kaley'"
    echo ""
    echo "Run this to create it:"
    echo "  ./deploy-gsc-credentials.sh"
fi
