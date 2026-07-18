FROM python:3.10-slim-bookworm

RUN sed -i \
    's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' \
    /etc/apt/sources.list.d/debian.sources

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    YOLO_FACTORY_SYSTEM_CONFIG=/app/configs/system.docker.yaml \
    YOLO_FACTORY_TASK_CONFIG_DIR=/data/task-configs \
    YOLO_FACTORY_MODEL_DIR=/models

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl ffmpeg libgl1 libglib2.0-0 libsm6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh

RUN python3.10 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3.10 -m pip install --no-cache-dir \
        torch==2.8.0 torchvision==0.23.0 \
        --index-url https://download.pytorch.org/whl/cpu \
    && python3.10 -m pip install --no-cache-dir . onnx==1.18.0 onnxruntime==1.22.1

RUN chmod +x /usr/local/bin/api-entrypoint.sh \
    && mkdir -p /data/task-configs /models

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=60s --retries=5 \
  CMD curl --fail --silent http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["api-entrypoint.sh"]
CMD ["python3.10", "-m", "uvicorn", "yolo_factory.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
