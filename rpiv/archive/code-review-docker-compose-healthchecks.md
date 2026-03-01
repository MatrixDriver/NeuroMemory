---
description: "代码审查报告: docker-compose-healthchecks"
status: archived
created_at: 2026-01-23T00:00:00
updated_at: 2026-01-29T00:00:00
archived_at: 2026-01-29T00:00:00
---

# Code Review: docker-compose.yml 健康检查与端口变更

> 对 `docker-compose.yml` 最近变更的技术审查（Neo4j / Qdrant 健康检查与 Qdrant 端口映射）。

---

## 统计

| 项目 | 数量 |
|------|------|
| 修改的文件 | 1 |
| 添加的文件 | 0 |
| 删除的文件 | 0 |
| 新增行 | 约 7 |
| 删除行 | 约 4 |

---

## 变更概要

- **Neo4j healthcheck**：`wget --no-verbose --tries=1 --spider localhost:7474` → `curl -f http://localhost:7474`
- **Qdrant ports**：统一使用 `6400:6400`（容器内外均为 6400）
- **Qdrant 环境变量**：新增 `QDRANT__SERVICE__HTTP_PORT=6400` 让 Qdrant 监听 6400

---

## 发现的问题

### 1. Qdrant 健康检查使用 `curl`，官方镜像中未安装

**severity:** high
**file:** `docker-compose.yml`
**line:** 31

**issue:**
健康检查命令为 `curl -f http://localhost:6400/ || exit 1`。`qdrant/qdrant` 官方镜像的 [Dockerfile](https://github.com/qdrant/qdrant/blob/master/Dockerfile) 基于 `debian:13-slim`，仅安装 `ca-certificates`、`tzdata`、`libunwind8` 及可选 `$PACKAGES`，**未安装 `curl`**。容器内执行 `curl` 会报错（如 `curl: not found`），healthcheck 会一直失败，容器被标为 `unhealthy`。

**detail:**
- 健康检查在**容器内**执行，需使用该镜像内存在的命令。
- `debian:13-slim` 及其在 Qdrant 镜像中的使用方式均未加入 `curl`。
- 若编排或上层服务依赖 `healthy` 状态，会导致启动/依赖判断失败。

**验证结果：**
在 `qdrant/qdrant:latest` 中执行 `which curl`、`which wget` 均无输出，**镜像内既无 curl 也无 wget**，当前健康检查会一直失败。

**suggestion:**

1. **方案 A（推荐）：暂时移除 Qdrant 的 healthcheck**
   仅依靠 `docker-compose up` 的启动顺序与应用层对 Qdrant 的调用失败做容错；待有自定义镜像或官方镜像提供 curl/wget 后再加回。

2. **方案 B：使用自定义镜像**
   编写 Dockerfile：`FROM qdrant/qdrant:latest`，然后
   `RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*`，构建并推送到自有仓库；在 `docker-compose.yml` 中将 `image: qdrant/qdrant:latest` 改为该镜像，健康检查可继续使用
   `curl -f http://localhost:6400/ || exit 1`。

---

### 2. Neo4j 健康检查改用 `curl` 的兼容性

**severity:** low
**file:** `docker-compose.yml`
**line:** 17

**issue:**
Neo4j 健康检查由 `wget --spider` 改为 `curl -f http://localhost:7474`。若 `neo4j:5.26.0` 镜像内未安装 `curl`，会与 Qdrant 同理出现 `unhealthy`。

**detail:**
Neo4j 官方镜像多基于完整版 Linux，不少版本会带 `curl`，但未在 Dockerfile 中统一承诺。`curl -f` 在 4xx/5xx 时会失败，用于"可访问即健康"的判定是合理的；主要风险在于 `curl` 是否存在。

**suggestion:**
- 若 `docker-compose up` 后 Neo4j 为 `unhealthy`，可改回 `wget` 或改用与当前镜像一致的命令，例如：
  ```yaml
  test: ["CMD-SHELL", "wget -q --spider http://localhost:7474 || exit 1"]
  ```
- 建议在本地或 CI 中跑一次 `docker-compose up -d` 后执行 `docker ps` 或 `docker inspect`，确认 `qdrant` 与 `neo4j` 的 `Health` 均为 `healthy`。

---

## 未发现问题的部分

- **Qdrant `localhost:6400`**：健康检查在容器内执行，Qdrant 通过 `QDRANT__SERVICE__HTTP_PORT=6400` 配置在容器内监听 6400，使用 `http://localhost:6400/` 正确。
- **端口 `6400:6400`**：宿主机与容器统一使用 6400，与 `config` 及文档中的配置一致。
- **`interval` / `timeout` / `retries`**：与 Neo4j 一致（10s / 5s / 5），无逻辑问题。
- **Neo4j `curl -f http://localhost:7474`**：在 `curl` 存在的前提下，用法正确；`-f` 对 4xx/5xx 的处置符合"不可用即失败"的语义。

---

## 建议的后续验证

1. **确认 Qdrant 镜像中 curl/wget 是否存在**：
   ```powershell
   docker run --rm --entrypoint /bin/sh qdrant/qdrant:latest -c "which curl; which wget"
   ```
2. **启动并检查健康状态**：
   ```powershell
   cd d:\CODE\NeuroMemory; docker-compose up -d; Start-Sleep -Seconds 25; docker ps --format "table {{.Names}}\t{{.Status}}"
   ```
   若 Qdrant 或 Neo4j 长期 `unhealthy`，按上文 1、2 的 suggestion 调整 `test` 或移除/自定义镜像。
3. **（可选）CI 中增加一步**：`docker-compose up -d` → `sleep` → `docker ps` 检查两服务均为 `healthy`，再跑依赖数据库的测试。

---

*审查完成。建议优先处理 Qdrant 健康检查中 `curl` 不可用的问题（high）；Neo4j 在使用 `curl` 时若出现 `unhealthy`，再按上述 low 项处理。*
