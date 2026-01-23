# EKS / Kubernetes 1.29 Upgrade Plan

## Goals
- Stop `AmazonEKS-Hours:extendedSupport` charges by running only supported versions.
- Upgrade control plane, add-ons, and worker nodes with minimal downtime and a verified rollback path.

## Scope & Assumptions
- Cluster: `inboxiq-eks` in `us-west-2`.
- Current version: 1.29 (Standard Support; plan also applies for future bumps).
- Node groups are managed; self-managed nodes follow the same drain/replace pattern.
- Kubectl access and AWS CLI are configured; maintenance window approved.

## High-Level Steps
1) Pre-checks and backups  
2) Control plane upgrade  
3) Core add-ons upgrade (VPC CNI, kube-proxy, CoreDNS)  
4) Managed node groups upgrade and drain  
5) Validation and smoke tests  
6) Rollback options and clean-up

## Implementation Artifacts
- Infra defaults updated to target `1.29` (prod `eks_cluster_version` default) and Terraform now tracks `version` so the control plane can be upgraded via `apply`.
- Helper script to run the end-to-end sequence: `scripts/upgrade_eks.sh` (overridable `TARGET_VERSION`, `CLUSTER_NAME`, `AWS_REGION`, and optional addon versions).
  - Example: `TARGET_VERSION=1.29 CLUSTER_NAME=inboxiq-eks AWS_REGION=us-west-2 scripts/upgrade_eks.sh`

## Pre-Checks (Day -1 or earlier)
- Confirm current versions:  
  - `aws eks describe-cluster --name inboxiq-eks --region us-west-2 --query 'cluster.version'`
  - `aws eks list-nodegroups --cluster-name inboxiq-eks --region us-west-2`
  - `aws eks describe-nodegroup --cluster-name inboxiq-eks --region us-west-2 --nodegroup-name <ng>`
- Capacity headroom: ensure each node group can surge by at least +1 for rolling upgrades (or temporarily raise `maxSize`).
- Add-on compatibility:  
  - `aws eks describe-addon-versions --addon-name vpc-cni --kubernetes-version <target>` (repeat for `kube-proxy`, `coredns`)
- Backups: export manifests/Helm values and ensure DB backups/snapshots are current.
- Freeze window: pause deploys during upgrade.

## Control Plane Upgrade (one minor at a time)
- Command:  
  `aws eks update-cluster-version --name inboxiq-eks --region us-west-2 --kubernetes-version <target>`
- Wait for `status: ACTIVE`:  
  `aws eks describe-cluster --name inboxiq-eks --region us-west-2 --query 'cluster.status'`

## Core Add-Ons
- Update to versions that match the target Kubernetes minor:  
  - `aws eks update-addon --cluster-name inboxiq-eks --region us-west-2 --addon-name vpc-cni --addon-version <match>`
  - `aws eks update-addon --cluster-name inboxiq-eks --region us-west-2 --addon-name kube-proxy --addon-version <match>`
  - `aws eks update-addon --cluster-name inboxiq-eks --region us-west-2 --addon-name coredns --addon-version <match>`
- Verify: `kubectl get pods -n kube-system`

## Managed Node Groups
- For each node group `<ng>`:  
  `aws eks update-nodegroup-version --cluster-name inboxiq-eks --region us-west-2 --nodegroup-name <ng>`
- Allow nodes to roll; ensure surge capacity is sufficient.
- Verify nodes: `kubectl get nodes` (all Ready, on target version).

## Validation (post-upgrade)
- Health checks: `kubectl get pods -A` (no CrashLoop), `kubectl get events -A | head`.
- App smoke tests: run API ping and a representative user flow.
- Logging/metrics: confirm ingestion and dashboards are normal.
- Cost check: next-day Cost Explorer should show no `extendedSupport` usage.

## Rollback Options
- Control plane: open AWS Support ticket to request downgrade if critical (last resort).
- Add-ons: reapply previous addon versions with `update-addon --addon-version <prev>`.
- Nodes: scale down new node group version and scale up previous AMI version (or restore ASG launch template).
- If needed, restore from backups/snapshots and redeploy pinned images.

## Communication & Change Control
- Announce maintenance window and potential brief disruption risk.
- Post-upgrade report: versions, timings, validation results, any issues and mitigations.

## Operational Tips
- Upgrade during low traffic; keep deploys frozen.
- Only one minor jump per run; repeat the same sequence for the next target version.
- Keep CloudWatch log retention trimmed to control costs.
