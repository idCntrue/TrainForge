import json
from pathlib import Path

from fastapi.testclient import TestClient

from yolo_factory.api.app import create_app
from yolo_factory.config.loader import load_task_config
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import (
    AnnotationExport,
    DatasetRelease,
    Task,
    VideoAsset,
    VideoCollection,
)


def _client(tmp_path: Path) -> tuple[TestClient, Path]:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    video_path = storage / "raw-videos" / "lights" / "batch-1" / "videos" / "sample.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"video-bytes")
    release_path = storage / "dataset-releases" / "lights" / "dataset-v1.0.0"
    release_path.mkdir(parents=True)

    with session_scope(registry) as session:
        session.add(
            Task(
                id="lights",
                task_type="detect",
                annotation_format="yolo-detect",
                classes_json=json.dumps(["red", "green"]),
            )
        )
    with session_scope(registry) as session:
        session.add(VideoCollection(id="batch-1", task_id="lights"))
        session.add(
            AnnotationExport(
                id="annotation-lights-rf-1",
                task_id="lights",
                provider_project="rf-lights",
                provider_version="1",
                zip_path="annotation-exports/lights/rf/1/original.zip",
                sha256="a" * 64,
            )
        )
    with session_scope(registry) as session:
        session.add(
            VideoAsset(
                id="video-lights-001",
                collection_id="batch-1",
                original_name="sample.mp4",
                stored_path=video_path.relative_to(storage).as_posix(),
                sha256="b" * 64,
                size_bytes=11,
            )
        )
        session.add(
            DatasetRelease(
                id="dataset-lights-1.0.0",
                task_id="lights",
                annotation_export_id="annotation-lights-rf-1",
                version="1.0.0",
                release_path=release_path.relative_to(storage).as_posix(),
                status="published",
            )
        )
    return TestClient(create_app(storage_root=storage)), storage


def test_dashboard_exposes_workflow_summary(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json() == {
        "annotation_exports": 1,
        "dataset_releases": 1,
        "frame_batches": 0,
        "tasks": 1,
        "video_assets": 1,
        "video_collections": 1,
    }


def test_cors_uses_configured_origins_without_credentials(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://factory.example.com, http://localhost:5173",
    )
    app = create_app(storage_root=tmp_path / "storage", training_engine="simulation")
    with TestClient(app) as client:
        allowed = client.options("/api/health", headers={
            "Origin": "https://factory.example.com",
            "Access-Control-Request-Method": "GET",
        })
        rejected = client.options("/api/health", headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "GET",
        })

    assert allowed.headers["access-control-allow-origin"] == "https://factory.example.com"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "access-control-allow-origin" not in rejected.headers


def test_lists_tasks_collections_and_releases(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/api/tasks").json() == [
        {
            "annotation_format": "yolo-detect",
            "class_display_names": {},
            "classes": ["red", "green"],
            "created_at": client.get("/api/tasks").json()[0]["created_at"],
            "id": "lights",
            "task_type": "detect",
        }
    ]
    collections = client.get("/api/video-collections").json()
    assert collections[0]["asset_count"] == 1
    assert collections[0]["total_size_bytes"] == 11
    releases = client.get("/api/dataset-releases").json()
    assert releases[0]["display_name"] == "lights"
    assert releases[0]["version"] == "1.0.0"
    assert releases[0]["status"] == "published"


def test_creates_task_and_persists_loadable_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "task-configs"
    client = TestClient(create_app(storage_root=tmp_path / "storage", task_config_dir=config_dir))

    response = client.post("/api/tasks", json={
        "id": "surface-defects",
        "task_type": "segment",
        "classes": ["scratch", "dent"],
        "class_display_names": {"scratch": "划痕", "dent": "凹痕"},
    })

    assert response.status_code == 201
    assert response.json()["annotation_format"] == "yolo-seg"
    assert response.json()["classes"] == ["scratch", "dent"]
    assert response.json()["class_display_names"] == {"scratch": "划痕", "dent": "凹痕"}
    config = load_task_config(config_dir / "surface-defects.yaml")
    assert config.task_id == "surface-defects"
    assert config.task_type == "segment"
    listed = client.get("/api/tasks").json()[0]
    assert listed["id"] == "surface-defects"
    assert listed["class_display_names"] == {"scratch": "划痕", "dent": "凹痕"}


def test_task_config_directory_can_come_from_environment(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "persistent-task-configs"
    monkeypatch.setenv("YOLO_FACTORY_TASK_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app(storage_root=tmp_path / "storage"))

    response = client.post("/api/tasks", json={
        "id": "cloud-defects",
        "task_type": "detect",
        "classes": ["scratch"],
    })

    assert response.status_code == 201
    assert load_task_config(config_dir / "cloud-defects.yaml").task_id == "cloud-defects"


def test_rejects_duplicate_task_id(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path / "storage", task_config_dir=tmp_path / "task-configs"))
    payload = {"id": "defects", "task_type": "detect", "classes": ["scratch"]}
    assert client.post("/api/tasks", json=payload).status_code == 201
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 409


def test_updates_existing_task_display_names_without_changing_classes(tmp_path: Path) -> None:
    config_dir = tmp_path / "task-configs"
    client = TestClient(create_app(storage_root=tmp_path / "storage", task_config_dir=config_dir))
    assert client.post("/api/tasks", json={
        "id": "elevator-signs",
        "task_type": "segment",
        "classes": ["elevator-id-tag", "entry-landing-indicator-light"],
    }).status_code == 201

    response = client.patch("/api/tasks/elevator-signs", json={
        "class_display_names": {
            "elevator-id-tag": "电梯编号标签",
            "entry-landing-indicator-light": "入口楼层指示灯",
        }
    })

    assert response.status_code == 200
    assert response.json()["classes"] == ["elevator-id-tag", "entry-landing-indicator-light"]
    assert response.json()["class_display_names"] == {
        "elevator-id-tag": "电梯编号标签",
        "entry-landing-indicator-light": "入口楼层指示灯",
    }
    assert load_task_config(config_dir / "elevator-signs.yaml").class_display_names == response.json()["class_display_names"]


def test_task_display_name_update_can_clear_mapping_and_rejects_unknown_class(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path / "storage", task_config_dir=tmp_path / "task-configs"))
    assert client.post("/api/tasks", json={
        "id": "defects",
        "task_type": "detect",
        "classes": ["scratch"],
        "class_display_names": {"scratch": "划痕"},
    }).status_code == 201

    cleared = client.patch("/api/tasks/defects", json={"class_display_names": {"scratch": ""}})
    rejected = client.patch("/api/tasks/defects", json={"class_display_names": {"dent": "凹痕"}})

    assert cleared.status_code == 200
    assert cleared.json()["class_display_names"] == {}
    assert rejected.status_code == 422
    assert client.get("/api/tasks").json()[0]["classes"] == ["scratch"]


def test_streams_only_registered_video_assets(tmp_path: Path) -> None:
    client, storage = _client(tmp_path)
    response = client.get("/api/video-assets/video-lights-001/content")
    assert response.status_code == 200
    assert response.content == b"video-bytes"
    assert client.get("/api/video-assets/unknown/content").status_code == 404
    (storage.parent / "secret.txt").write_text("secret", encoding="utf-8")
    assert client.get("/api/video-assets/../../secret/content").status_code == 404
