#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S_DIR="${ROOT_DIR}/src/k8s"
TF_DIR="${ROOT_DIR}/infra/environments/production"
MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-monitoring}"
APP_NAMESPACE="${APP_NAMESPACE:-kaley}"
RELEASE_NAME="${RELEASE_NAME:-kube-prometheus-stack}"
GRAFANA_STORAGE_CLASS="${GRAFANA_STORAGE_CLASS:-efs-observability}"
PROMETHEUS_STORAGE_CLASS="${PROMETHEUS_STORAGE_CLASS:-ebs-gp3-csi}"
MIGRATE_PROMETHEUS_PVC="${MIGRATE_PROMETHEUS_PVC:-false}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd kubectl
require_cmd helm
require_cmd terraform
require_cmd envsubst

apply_storage_classes() {
  local rendered
  local current_efs_fs_id
  rendered="$(envsubst < "${K8S_DIR}/storageclasses.yaml")"

  if ! kubectl get storageclass ebs-gp3-csi >/dev/null 2>&1; then
    printf '%s\n' "${rendered}" | kubectl apply -f -
    return
  fi

  if ! kubectl get storageclass efs-observability >/dev/null 2>&1; then
    printf '%s\n' "${rendered}" | kubectl apply -f -
    return
  fi

  current_efs_fs_id="$(kubectl get storageclass efs-observability -o jsonpath='{.parameters.fileSystemId}' 2>/dev/null || true)"
  if [[ -z "${current_efs_fs_id}" || "${current_efs_fs_id}" != "${EFS_FILE_SYSTEM_ID}" ]]; then
    echo "Recreating efs-observability StorageClass with fileSystemId=${EFS_FILE_SYSTEM_ID}..."
    kubectl delete storageclass efs-observability
    printf '%s\n' "${rendered}" | kubectl apply -f -
    return
  fi

  echo "Storage classes already exist with the expected parameters; skipping immutable StorageClass apply."
}

pvc_storage_class() {
  local namespace="$1"
  local name="$2"
  kubectl get pvc "${name}" -n "${namespace}" -o jsonpath='{.spec.storageClassName}' 2>/dev/null || true
}

migrate_grafana_pvc_if_needed() {
  local current_class
  current_class="$(pvc_storage_class "${MONITORING_NAMESPACE}" "${RELEASE_NAME}-grafana")"

  if [[ -z "${current_class}" ]]; then
    echo "Grafana PVC does not exist yet; no migration needed."
    return
  fi

  if [[ "${current_class}" == "${GRAFANA_STORAGE_CLASS}" ]]; then
    echo "Grafana PVC already uses ${GRAFANA_STORAGE_CLASS}; no migration needed."
    return
  fi

  echo "Migrating Grafana PVC from ${current_class} to ${GRAFANA_STORAGE_CLASS}..."
  kubectl scale deployment/"${RELEASE_NAME}"-grafana -n "${MONITORING_NAMESPACE}" --replicas=0
  kubectl wait --for=delete pod -l app.kubernetes.io/name=grafana -n "${MONITORING_NAMESPACE}" --timeout=300s || true
  kubectl delete pvc "${RELEASE_NAME}-grafana" -n "${MONITORING_NAMESPACE}"
}

migrate_prometheus_pvc_if_requested() {
  local current_class
  local pvc_name="prometheus-${RELEASE_NAME}-prometheus-db-prometheus-${RELEASE_NAME}-prometheus-0"

  current_class="$(pvc_storage_class "${MONITORING_NAMESPACE}" "${pvc_name}")"

  if [[ -z "${current_class}" ]]; then
    echo "Prometheus PVC does not exist yet; no migration needed."
    return
  fi

  if [[ "${current_class}" == "${PROMETHEUS_STORAGE_CLASS}" ]]; then
    echo "Prometheus PVC already uses ${PROMETHEUS_STORAGE_CLASS}; no migration needed."
    return
  fi

  if [[ "${MIGRATE_PROMETHEUS_PVC}" != "true" ]]; then
    cat <<EOF
Prometheus PVC still uses ${current_class}.
It was left in place intentionally because migrating it deletes existing metrics history.

To recreate it on ${PROMETHEUS_STORAGE_CLASS}, re-run with:
  MIGRATE_PROMETHEUS_PVC=true ./src/k8s/deploy-monitoring.sh
EOF
    return
  fi

  echo "Migrating Prometheus PVC from ${current_class} to ${PROMETHEUS_STORAGE_CLASS}..."
  kubectl scale statefulset/prometheus-"${RELEASE_NAME}"-prometheus -n "${MONITORING_NAMESPACE}" --replicas=0
  kubectl wait --for=delete pod -l app.kubernetes.io/name=prometheus -n "${MONITORING_NAMESPACE}" --timeout=300s || true
  kubectl delete pvc "${pvc_name}" -n "${MONITORING_NAMESPACE}"
}

echo "Checking Kubernetes access..."
kubectl cluster-info >/dev/null

echo "Resolving observability EFS file system id from Terraform output..."
EFS_FILE_SYSTEM_ID="${EFS_FILE_SYSTEM_ID:-$(terraform -chdir="${TF_DIR}" output -raw observability_efs_file_system_id)}"
export EFS_FILE_SYSTEM_ID

echo "Checking CSI driver prerequisites..."
kubectl get csidriver ebs.csi.aws.com >/dev/null
if ! kubectl get csidriver efs.csi.aws.com >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Missing EFS CSI driver (efs.csi.aws.com) in the cluster.

This repo now uses EFS-backed storage for Grafana to avoid node-loss/EBS attachment issues.
Install the AWS EFS CSI driver first, then re-run this script.
EOF
  exit 1
fi

if ! kubectl get deployment efs-csi-controller -n kube-system >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Missing EFS CSI controller deployment in kube-system.

The cluster may still have a stale CSIDriver object, but dynamic EFS provisioning will not work
without the controller deployment.
Install the AWS EFS CSI driver first, then re-run this script.
EOF
  exit 1
fi

if ! kubectl get daemonset efs-csi-node -n kube-system >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Missing EFS CSI node daemonset in kube-system.

Dynamic EFS provisioning and mounts will not work until the AWS EFS CSI node daemonset is installed.
Install the AWS EFS CSI driver first, then re-run this script.
EOF
  exit 1
fi

echo "Creating namespaces if needed..."
kubectl create namespace "${MONITORING_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace "${APP_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "Applying cluster-scoped and app-side monitoring manifests..."
kubectl apply -f "${K8S_DIR}/priority-classes.yaml"
apply_storage_classes
kubectl apply -f "${K8S_DIR}/inboxiq-flask-servicemonitor.yaml"
kubectl apply -f "${K8S_DIR}/celery-exporter.yaml"
kubectl apply -f "${K8S_DIR}/grafana-cost-dashboard.yaml"
kubectl apply -f "${K8S_DIR}/grafana-ingress.yaml"

echo "Installing or upgrading kube-prometheus-stack via Helm..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update prometheus-community >/dev/null

migrate_grafana_pvc_if_needed
migrate_prometheus_pvc_if_requested

helm upgrade --install "${RELEASE_NAME}" prometheus-community/kube-prometheus-stack \
  --namespace "${MONITORING_NAMESPACE}" \
  --create-namespace \
  -f "${K8S_DIR}/prometheus-values.yaml"

echo "Waiting for Grafana and Prometheus pods..."
kubectl rollout status deployment/"${RELEASE_NAME}"-grafana -n "${MONITORING_NAMESPACE}" --timeout=600s
kubectl rollout status statefulset/prometheus-"${RELEASE_NAME}"-prometheus -n "${MONITORING_NAMESPACE}" --timeout=600s

echo "Monitoring deploy complete."
