from yolo_factory.datasets.splitting import (
    Sample,
    create_initial_split,
    extend_split,
)


def _samples(prefix: str, video_count: int, frames: int = 2) -> list[Sample]:
    return [
        Sample(
            sample_id=f"{prefix}-{video_index}-{frame_index}",
            source_video_id=f"{prefix}-video-{video_index}",
        )
        for video_index in range(video_count)
        for frame_index in range(frames)
    ]


def test_initial_split_is_seeded_and_source_grouped() -> None:
    samples = _samples("base", 10)
    first = create_initial_split(samples, seed=42)
    second = create_initial_split(list(reversed(samples)), seed=42)
    assert first == second
    assert len(first.train) == 16
    assert len(first.val) == 2
    assert len(first.test) == 2

    membership = {
        sample_id: split
        for split, sample_ids in (
            ("train", first.train),
            ("val", first.val),
            ("test", first.test),
        )
        for sample_id in sample_ids
    }
    for video_index in range(10):
        assert len(
            {
                membership[f"base-{video_index}-{frame_index}"]
                for frame_index in range(2)
            }
        ) == 1


def test_extension_preserves_test_and_adds_only_train_or_val() -> None:
    baseline = create_initial_split(_samples("base", 10), seed=42)
    extended = extend_split(baseline, _samples("new", 5), seed=42)
    assert extended.test == baseline.test
    assert set(baseline.train) <= set(extended.train)
    assert set(baseline.val) <= set(extended.val)
    assert not any(sample_id.startswith("new-") for sample_id in extended.test)
    assert len(extended.all_ids) == 30


def test_rejects_source_video_already_split_across_baseline() -> None:
    baseline = create_initial_split(_samples("base", 10), seed=42)
    duplicate_source = [
        Sample(sample_id="new-frame", source_video_id="base-video-0")
    ]
    try:
        extend_split(baseline, duplicate_source, seed=42)
    except ValueError as error:
        assert "source video" in str(error)
    else:
        raise AssertionError("expected source video reuse rejection")
