#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S_DIR="$ROOT_DIR/k8s/orbstack"
EXPECTED_CONTEXT="${KUBECTL_CONTEXT:-orbstack}"
NAMESPACE="mooomoocat-rag"
ECK_VERSION="${ECK_VERSION:-3.4.0}"
ECK_OPERATOR_URL="https://download.elastic.co/downloads/eck/${ECK_VERSION}/operator.yaml"
REMOVE_ECK_OPERATOR="${REMOVE_ECK_OPERATOR:-false}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令: $1" >&2
    exit 1
  fi
}

require_cluster() {
  local current_context
  current_context="$(kubectl config current-context 2>/dev/null || true)"

  if [[ "$current_context" != "$EXPECTED_CONTEXT" ]]; then
    echo "当前 kubectl context 是 '$current_context'，期望为 '$EXPECTED_CONTEXT'。" >&2
    echo "如需切换，可执行: kubectl config use-context $EXPECTED_CONTEXT" >&2
    exit 1
  fi

  if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "无法连接 Kubernetes API Server，请先确认 OrbStack Kubernetes 仍处于启动状态。" >&2
    exit 1
  fi
}

require_cmd kubectl
require_cluster

echo ">>> 删除 repo-local 依赖资源"
kubectl delete -k "$K8S_DIR" --ignore-not-found=true
kubectl delete namespace "$NAMESPACE" --ignore-not-found=true --wait=false

if [[ "$REMOVE_ECK_OPERATOR" == "true" ]]; then
  echo ">>> 删除 ECK operator (${ECK_VERSION})"
  kubectl delete -f "$ECK_OPERATOR_URL" --ignore-not-found=true
else
  echo ">>> 保留 ECK operator。若要一并删除，请执行:"
  echo "    REMOVE_ECK_OPERATOR=true bash/k8s/stop-deps.sh"
fi
