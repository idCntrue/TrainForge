import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_default_api_image_uses_cpu_pytorch_and_runtime_dependencies() -> None:
    dockerfile = _text("docker/api.Dockerfile")
    entrypoint = _text("docker/api-entrypoint.sh")
    assert "FROM python:3.10-slim" in dockerfile
    assert "mirrors.aliyun.com/debian" in dockerfile
    assert "mirrors.aliyun.com/pypi/simple" in dockerfile
    assert "https://download.pytorch.org/whl/cpu" in dockerfile
    assert "nvidia/cuda" not in dockerfile
    assert "cu128" not in dockerfile
    assert "ffmpeg" in dockerfile
    assert "onnxruntime" in dockerfile
    assert "uvicorn" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "ENTRYPOINT" in dockerfile
    assert "yolo-factory init-storage" in entrypoint
    assert 'exec "$@"' in entrypoint


def test_ultralytics_version_is_pinned_for_reproducible_builds() -> None:
    project = _text("pyproject.toml")
    requirements = _text("requirements/data.txt")
    assert '"ultralytics==8.4.95"' in project
    assert "ultralytics==8.4.95" in requirements


def test_web_image_is_multistage_and_nginx_proxies_same_origin_api() -> None:
    dockerfile = _text("docker/web.Dockerfile")
    nginx = _text("docker/nginx.conf")
    assert "FROM node:" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "FROM nginx:" in dockerfile
    assert "location /api/" in nginx
    assert "proxy_pass http://api:8000;" in nginx
    assert "client_max_body_size" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx


def test_base_compose_runs_without_gpu_and_keeps_persistent_mounts_and_healthchecks() -> None:
    compose = yaml.safe_load(_text("compose.yaml"))
    assert set(compose["services"]) == {"api", "web"}
    api = compose["services"]["api"]
    web = compose["services"]["web"]
    assert "${DATA_DIR:-./docker-data}:/data" in api["volumes"]
    assert "${MODEL_DIR:-./models}:/models:ro" in api["volumes"]
    assert "deploy" not in api
    assert api["mem_limit"] == "${API_MEMORY_LIMIT:-10g}"
    assert api["cpus"] == "${API_CPU_LIMIT:-6}"
    assert api["shm_size"] == "${API_SHM_SIZE:-2gb}"
    assert api["pids_limit"] == "${API_PIDS_LIMIT:-256}"
    assert api["healthcheck"]["test"]
    assert api["restart"] == "unless-stopped"
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert web["restart"] == "unless-stopped"


def test_gpu_overlay_requests_nvidia_device_only_when_selected() -> None:
    overlay = yaml.safe_load(_text("compose.gpu.yaml"))
    api = overlay["services"]["api"]
    gpu_dockerfile = _text("docker/api.gpu.Dockerfile")
    assert api["build"]["dockerfile"] == "docker/api.gpu.Dockerfile"
    assert "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04" in gpu_dockerfile
    assert "torch==2.8.0 torchvision==0.23.0" in gpu_dockerfile
    assert "https://download.pytorch.org/whl/cu128" in gpu_dockerfile
    devices = api["deploy"]["resources"]["reservations"]["devices"]
    assert devices[0]["driver"] == "nvidia"
    assert devices[0]["capabilities"] == ["gpu"]


def test_docker_context_excludes_local_data_weights_and_build_outputs() -> None:
    dockerignore = _text(".dockerignore")
    for pattern in [".git", ".env", "*.pt", "docker-data", "frontend/node_modules", "frontend/dist"]:
        assert pattern in dockerignore


def test_readme_documents_cpu_gpu_and_migration_commands() -> None:
    readme = _text("README.md")
    assert "docker compose up -d --build" in readme
    assert "compose.gpu.yaml" in readme
    assert "migrate-storage-paths" in readme
    assert "--apply" in readme
    assert "/srv/yolo-factory/data" in readme
    assert ".env" in _text(".gitignore")


def test_active_frontend_does_not_display_a_hardcoded_local_api_address() -> None:
    source = _text("frontend/src/App.tsx")
    assert "http://127.0.0.1:8000/api" not in source
    assert "window.location.origin" in source


def test_one_command_deploy_builds_tagged_images_backs_up_and_checks_health() -> None:
    script = _text("docker/deploy.sh")
    assert "docker compose config" in script
    assert "docker compose build" in script
    assert "factory.db" in script
    assert "IMAGE_TAG" in script
    assert "docker compose up -d --no-build" in script
    assert "/api/health" in script
    assert "rollback" in script.lower()
    assert "docker compose ps -q api" in script


def test_docker_environment_documents_training_resource_limits() -> None:
    environment = _text(".env.docker.example")
    for setting in [
        "API_MEMORY_LIMIT=10g",
        "API_CPU_LIMIT=6",
        "API_SHM_SIZE=2gb",
        "API_PIDS_LIMIT=256",
        "CPU_TRAINING_THREADS=4",
        "CPU_DETECT_MAX_BATCH=4",
        "CPU_SEGMENT_MAX_BATCH=1",
        "CPU_TRAINING_MAX_IMAGE_SIZE=640",
        "GPU_DETECT_MAX_BATCH=8",
        "GPU_SEGMENT_MAX_BATCH=2",
        "GPU_TRAINING_MAX_IMAGE_SIZE=1280",
        "GPU_ALLOWED_DEVICES=",
        "YOLO_FACTORY_MAX_UPLOAD_BYTES=2147483648",
        "TRAINING_MIN_FREE_DISK_GB=10",
        "TRAINING_MIN_FREE_DISK_PERCENT=10",
        "CORS_ALLOWED_ORIGINS=",
    ]:
        assert setting in environment
    assert "YOLO_FACTORY_MAX_UPLOAD_BYTES: ${YOLO_FACTORY_MAX_UPLOAD_BYTES:-2147483648}" in _text("compose.yaml")
    assert "client_max_body_size 2g;" in _text("docker/nginx.conf")


def test_github_workflow_tests_packages_and_ssh_deploys_without_secrets_in_source() -> None:
    workflow = _text(".github/workflows/deploy.yml")
    assert "workflow_dispatch" in workflow
    assert "pytest" in workflow
    assert "npm test" in workflow
    assert "npm run build" in workflow
    assert "DEPLOY_HOST" in workflow
    assert "DEPLOY_SSH_KEY" in workflow
    assert "docker/deploy.sh" in workflow
    assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", workflow)
