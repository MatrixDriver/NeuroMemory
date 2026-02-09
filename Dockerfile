# NeuroMemory Dockerfile for Railway Deployment
# 多阶段构建优化镜像大小
FROM python:3.13-slim as builder

WORKDIR /app

# 安装 uv（更快的依赖安装工具）
RUN pip install --no-cache-dir uv

# 复制所有源代码和依赖文件
COPY . ./

# 安装依赖（不包含 dev 依赖，减小镜像体积）
RUN uv pip install --system --no-cache-dir -e .

# 运行阶段
FROM python:3.13-slim

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制 Python 环境
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制源代码
COPY . ./

# 创建非 root 用户（安全最佳实践）
# -m 创建 home 目录，mem0 库需要在 ~/.mem0 写入配置
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 -m appuser && \
    chown -R appuser:appuser /app
USER appuser

# 暴露端口（EXPOSE 仅文档用，实际监听 PORT 或 8765）
EXPOSE 8765

# 健康检查（使用 PORT 以兼容 Railway 等 PaaS 的端口注入）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD ["sh", "-c", "curl -f http://localhost:${PORT:-8765}/health || exit 1"]

# 启动命令：优先使用 PORT 环境变量（Railway 注入），否则 8765
CMD ["sh", "-c", "uvicorn http_server:app --host 0.0.0.0 --port ${PORT:-8765} --workers 2"]
