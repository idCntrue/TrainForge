import time
from pathlib import Path

from fastapi.testclient import TestClient

from yolo_factory.api.app import create_app


def _create_task(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={"id": "inspection", "task_type": "detect", "classes": ["defect"]},
    )
    assert response.status_code == 201


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("video import job did not finish")


def test_uploads_multiple_videos_and_cleans_staging_directory(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    task_config_dir = tmp_path / "task-configs"
    with TestClient(
        create_app(
            storage_root=storage,
            task_config_dir=task_config_dir,
            training_engine="simulation",
        )
    ) as client:
        _create_task(client)
        (task_config_dir / "inspection.yaml").unlink()
        response = client.post(
            "/api/video-collections/upload",
            data={"task_id": "inspection", "collection_id": "upload-001"},
            files=[
                ("files", ("camera-1.mp4", b"video-one", "video/mp4")),
                ("files", ("camera-2.MOV", b"video-two", "video/quicktime")),
            ],
        )
        assert response.status_code == 202, response.text
        assert response.json()["uploaded_count"] == 2
        job = _wait_for_job(client, response.json()["job_id"])
        assert job["status"] == "completed", job

        collections = client.get("/api/video-collections").json()
        assert collections[0]["id"] == "upload-001"
        assert collections[0]["asset_count"] == 2

    staging_root = storage / "imports" / "video-uploads"
    assert not staging_root.exists() or list(staging_root.iterdir()) == []


def test_rejects_non_video_upload_without_leaving_staging_files(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    with TestClient(
        create_app(
            storage_root=storage,
            task_config_dir=tmp_path / "task-configs",
            training_engine="simulation",
        )
    ) as client:
        _create_task(client)
        response = client.post(
            "/api/video-collections/upload",
            data={"task_id": "inspection", "collection_id": "upload-invalid"},
            files=[("files", ("notes.txt", b"not-video", "text/plain"))],
        )

    assert response.status_code == 422
    assert "unsupported video extension" in response.json()["detail"]
    staging_root = storage / "imports" / "video-uploads"
    assert not staging_root.exists() or list(staging_root.iterdir()) == []


def test_server_directory_import_is_limited_to_imports_root(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    outside = tmp_path / "outside"
    outside.mkdir()
    task_config_dir = tmp_path / "task-configs"
    with TestClient(
        create_app(
            storage_root=storage,
            task_config_dir=task_config_dir,
            training_engine="simulation",
        )
    ) as client:
        _create_task(client)
        (task_config_dir / "inspection.yaml").unlink()
        response = client.post(
            "/api/video-collections",
            json={
                "task_id": "inspection",
                "collection_id": "outside-import",
                "source_dir": str(outside),
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "source directory must be inside the storage imports directory"
