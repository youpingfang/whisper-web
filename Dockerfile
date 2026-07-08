# ===== 构建阶段: 前端 =====
FROM node:22-slim AS builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN npm install -g pnpm && \
    pnpm install --ignore-scripts && \
    pnpm rebuild esbuild
COPY frontend/ .
RUN pnpm run build

# ===== 运行阶段: Python 后端 =====
FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制后端源码
COPY backend/ .

# 复制前端构建产物
COPY --from=builder /build/frontend/dist /app/static

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    faster-whisper \
    sse-starlette \
    yt-dlp \
    opencc-python-reimplemented

# 目录准备
RUN mkdir -p uploads whisper_files downloads 2>/dev/null; \
    touch uploads/.gitkeep whisper_files/.gitkeep

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
