from pathlib import Path

from yolo_factory.annotations.sam_executor import LocalSamExecutor


def test_sam_executor_reuses_each_loaded_model(tmp_path: Path) -> None:
    constructed: list[str] = []

    def model_factory(model_path: str):
        constructed.append(model_path)
        return object()

    def predictor(model, payload):
        return {"polygon": [0.1, 0.1, 0.9, 0.1, 0.5, 0.9], "model": payload["model"]}

    executor = LocalSamExecutor(tmp_path, model_factory=model_factory, predictor=predictor)
    first, first_directory = executor.run("frame-1", {"model": "sam2_t.pt", "image_path": "image.jpg", "point": [0.5, 0.5]})
    second, _ = executor.run("frame-1", {"model": "sam2_t.pt", "image_path": "image.jpg", "point": [0.6, 0.6]})
    third, _ = executor.run("frame-1", {"model": "sam2_s.pt", "image_path": "image.jpg", "point": [0.5, 0.5]})

    assert constructed == ["sam2_t.pt", "sam2_s.pt"]
    assert first["model_was_loaded"] is True
    assert second["model_was_loaded"] is False
    assert third["model_was_loaded"] is True
    assert (first_directory / "manifest.json").is_file()
    assert (first_directory / "result.json").is_file()


def test_sam_executor_resolves_named_weights_from_model_directory(tmp_path: Path, monkeypatch) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    weight = model_dir / "sam2_t.pt"
    weight.write_bytes(b"weights")
    monkeypatch.setenv("YOLO_FACTORY_MODEL_DIR", str(model_dir))
    constructed: list[str] = []

    executor = LocalSamExecutor(
        tmp_path / "storage",
        model_factory=lambda model_path: constructed.append(model_path) or object(),
        predictor=lambda model, payload: {"polygon": [0.1, 0.1, 0.9, 0.1, 0.5, 0.9]},
    )
    executor.run("frame-1", {"model": "sam2_t.pt", "image_path": "image.jpg", "point": [0.5, 0.5]})

    assert constructed == [str(weight.resolve())]
