#!/usr/bin/env bash
set -euo pipefail

EXPECTED_CONTEXT="${KUBECTL_CONTEXT:-orbstack}"
NAMESPACE="mooomoocat-rag"
ELASTICSEARCH_SERVICE="service/mooomoocat-es-es-http"
QDRANT_SERVICE="service/qdrant"
MODE="${1:-all}"

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
    echo "无法连接 Kubernetes API Server，请先确认 OrbStack Kubernetes 已启动。" >&2
    exit 1
  fi
}

start_all() {
  local qdrant_log es_log qdrant_pid es_pid
  qdrant_log="$(mktemp -t qdrant-port-forward.XXXXXX.log)"
  es_log="$(mktemp -t elasticsearch-port-forward.XXXXXX.log)"

  kubectl -n "$NAMESPACE" port-forward "$QDRANT_SERVICE" 6333:6333 6334:6334 >"$qdrant_log" 2>&1 &
  qdrant_pid=$!
  kubectl -n "$NAMESPACE" port-forward "$ELASTICSEARCH_SERVICE" 9200:9200 >"$es_log" 2>&1 &
  es_pid=$!

  cleanup() {
    kill "$qdrant_pid" "$es_pid" 2>/dev/null || true
    rm -f "$qdrant_log" "$es_log"
  }
  trap cleanup EXIT INT TERM

  cat <<EOF
Qdrant:
  http://127.0.0.1:6333
  grpc://127.0.0.1:6334
Elasticsearch:
  https://127.0.0.1:9200

按 Ctrl-C 结束 port-forward。
EOF

  wait "$qdrant_pid" "$es_pid"
}

require_cmd kubectl
require_cluster

case "$MODE" in
  qdrant)
    exec kubectl -n "$NAMESPACE" port-forward "$QDRANT_SERVICE" 6333:6333 6334:6334
    ;;
  es|elasticsearch)
    exec kubectl -n "$NAMESPACE" port-forward "$ELASTICSEARCH_SERVICE" 9200:9200
    ;;
  all)
    start_all
    ;;
  *)
    echo "用法: bash/k8s/port-forward.sh [all|qdrant|es]" >&2
    exit 1
    ;;
esac
