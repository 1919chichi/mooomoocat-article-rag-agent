#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S_DIR="$ROOT_DIR/k8s/orbstack"
EXPECTED_CONTEXT="${KUBECTL_CONTEXT:-orbstack}"
NAMESPACE="mooomoocat-rag"
ECK_VERSION="${ECK_VERSION:-3.4.0}"
ECK_OPERATOR_URL="https://download.elastic.co/downloads/eck/${ECK_VERSION}/operator.yaml"
ELASTICSEARCH_NAME="mooomoocat-es"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令: $1" >&2
    exit 1
  fi
}

require_cluster() {
  local current_context
  current_context="$(kubectl config current-context 2>/dev/null || true)"

  if [[ -z "$current_context" ]]; then
    echo "kubectl 当前没有可用 context，请先在 OrbStack 中启用 Kubernetes。" >&2
    exit 1
  fi

  if [[ "$current_context" != "$EXPECTED_CONTEXT" ]]; then
    echo "当前 kubectl context 是 '$current_context'，期望为 '$EXPECTED_CONTEXT'。" >&2
    echo "如需切换，可执行: kubectl config use-context $EXPECTED_CONTEXT" >&2
    exit 1
  fi

  if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "无法连接 Kubernetes API Server。" >&2
    echo "如果你最近看到 connection refused，请先在 OrbStack 中确认 Kubernetes 已启动，再重试。" >&2
    exit 1
  fi
}

wait_for_jsonpath() {
  local resource="$1"
  local namespace="$2"
  local jsonpath="$3"
  local expected="$4"
  local timeout_seconds="$5"
  local deadline=$((SECONDS + timeout_seconds))
  local current=""

  while (( SECONDS < deadline )); do
    current="$(kubectl get "$resource" -n "$namespace" -o "jsonpath=${jsonpath}" 2>/dev/null || true)"
    if [[ "$current" == "$expected" ]]; then
      return 0
    fi
    sleep 5
  done

  echo "等待 $resource 超时，期望 ${jsonpath}=${expected}，实际值='${current}'。" >&2
  return 1
}

require_cmd kubectl
require_cluster

echo ">>> 安装或更新 ECK operator (${ECK_VERSION})"
kubectl apply -f "$ECK_OPERATOR_URL"
kubectl rollout status statefulset/elastic-operator -n elastic-system --timeout=5m

echo ">>> 应用 repo-local 依赖清单"
kubectl apply -k "$K8S_DIR"

echo ">>> 等待 Qdrant 就绪"
kubectl rollout status statefulset/qdrant -n "$NAMESPACE" --timeout=5m

echo ">>> 等待 Elasticsearch Pod 创建并就绪"
wait_for_jsonpath "elasticsearch/${ELASTICSEARCH_NAME}" "$NAMESPACE" "{.status.phase}" "Ready" 600

cat <<EOF
>>> 依赖已启动完成
namespace: ${NAMESPACE}
Qdrant service: qdrant.${NAMESPACE}.svc.cluster.local:6333
Elasticsearch service: ${ELASTICSEARCH_NAME}-es-http.${NAMESPACE}.svc.cluster.local:9200

如需本机访问，请执行:
  bash/k8s/port-forward.sh
EOF
