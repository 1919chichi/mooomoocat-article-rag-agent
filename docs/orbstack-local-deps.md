# OrbStack 本地依赖部署说明

本文档说明如何在本仓库里使用 OrbStack Kubernetes 启动 `Qdrant + Elasticsearch` 依赖，并通过本机 `port-forward` 给 CLI 使用。

## 1. 前置检查

### 1.1 确认 OrbStack Kubernetes 已启动

当前脚本默认要求：

- `kubectl` 已安装。
- `kubectl` 当前 context 是 `orbstack`。
- OrbStack 的 Kubernetes API Server 已经启动。

先执行：

```bash
kubectl config current-context
kubectl cluster-info
```

预期：

- `kubectl config current-context` 输出 `orbstack`
- `kubectl cluster-info` 能正常返回 control plane 信息

如果你看到类似 `connection refused`，不要直接继续执行脚本。先回到 OrbStack，确认 Kubernetes 开关已经打开并完成启动，再重试上面的命令。

如需切换 context：

```bash
kubectl config use-context orbstack
```

### 1.2 确认本机 kubectl 版本可用

当前仓库没有额外依赖 `helm` 或 `kustomize` 独立二进制，脚本只使用 `kubectl`。建议先确认：

```bash
kubectl version --client
```

### 1.3 版本基线

当前仓库清单默认值：

- ECK operator：`3.4.0`
- Elasticsearch：`9.2.3`
- Qdrant：`qdrant/qdrant:v1.18.0`
- namespace：`mooomoocat-rag`

其中 ECK operator 版本可以通过环境变量覆盖：

```bash
ECK_VERSION=3.4.0 bash/k8s/start-deps.sh
```

## 2. 启动依赖

执行：

```bash
bash/k8s/start-deps.sh
```

脚本会依次做这些事：

1. 校验当前 `kubectl` context 是否为 `orbstack`
2. 校验 API Server 是否可访问
3. 安装或更新 ECK operator
4. 应用 `k8s/orbstack/` 下的 repo-local 清单
5. 等待 Qdrant 和 Elasticsearch 进入可用状态

如果只想看资源状态，可以额外执行：

```bash
kubectl get pods -n mooomoocat-rag
kubectl get elasticsearch -n mooomoocat-rag
kubectl get pvc -n mooomoocat-rag
```

## 3. 本机 port-forward

### 3.1 同时转发 Qdrant 和 Elasticsearch

```bash
bash/k8s/port-forward.sh
```

默认会建立：

- `http://127.0.0.1:6333` -> Qdrant REST / Dashboard
- `grpc://127.0.0.1:6334` -> Qdrant gRPC
- `https://127.0.0.1:9200` -> Elasticsearch HTTPS

按 `Ctrl-C` 结束。

### 3.2 只转发单个依赖

```bash
bash/k8s/port-forward.sh qdrant
bash/k8s/port-forward.sh es
```

## 4. 读取 Elasticsearch 凭据和 CA

ECK 会自动创建 `elastic` 用户密码和 HTTP CA 证书。

### 4.1 读取 `elastic` 用户密码

```bash
kubectl get secret mooomoocat-es-es-elastic-user \
  -n mooomoocat-rag \
  -o go-template='{{.data.elastic | base64decode}}'
echo
```

### 4.2 导出 CA 证书到本地

```bash
kubectl get secret mooomoocat-es-es-http-certs-public \
  -n mooomoocat-rag \
  -o go-template='{{index .data "tls.crt" | base64decode}}' > /tmp/mooomoocat-es-ca.crt
```

### 4.3 本机连通性检查

```bash
curl --cacert /tmp/mooomoocat-es-ca.crt \
  -u elastic:"$(kubectl get secret mooomoocat-es-es-elastic-user -n mooomoocat-rag -o go-template='{{.data.elastic | base64decode}}')" \
  https://127.0.0.1:9200
```

如果你的 CLI 后续需要配置本机连接，典型配置会是：

```env
QDRANT_URL=http://127.0.0.1:6333
ELASTICSEARCH_URL=https://127.0.0.1:9200
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=<从 secret 读取>
ELASTICSEARCH_CA_CERT_PATH=/tmp/mooomoocat-es-ca.crt
```

## 5. 停止和清理

停止 repo-local 依赖：

```bash
bash/k8s/stop-deps.sh
```

默认行为：

- 删除 `k8s/orbstack/` 对应的 namespace 内资源
- 删除 `mooomoocat-rag` namespace
- 保留 `elastic-system` 里的 ECK operator，避免反复重装 CRD

如果你连 operator 也想一起删掉：

```bash
REMOVE_ECK_OPERATOR=true bash/k8s/stop-deps.sh
```

## 6. 目录说明

```text
k8s/orbstack/
  namespace.yaml
  kustomization.yaml
  qdrant/
    service.yaml
    statefulset.yaml
  eck/
    elasticsearch.yaml

bash/k8s/
  start-deps.sh
  stop-deps.sh
  port-forward.sh
```

## 7. 已知限制

- 当前基线只覆盖本地单节点依赖，不是生产级 HA 配置。
- Elasticsearch 通过 ECK 管理，第一次拉镜像和初始化可能需要几分钟。
- 如果 OrbStack Kubernetes 没启动，即使 `kubectl` context 仍显示 `orbstack`，脚本也会因为 API Server 不可达而失败，这是预期保护。
