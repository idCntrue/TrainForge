from pathlib import Path

from PIL import Image, ImageDraw

from yolo_factory.frames.deduplication import find_duplicate_groups


def _base_image(path: Path, quality: int = 95) -> None:
    image = Image.new("RGB", (128, 128), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 80, 80), fill="black")
    image.save(path, quality=quality)


def test_groups_recompressed_copy_and_keeps_different_image(
    tmp_path: Path,
) -> None:
    original = tmp_path / "t-000000000ms.jpg"
    recompressed = tmp_path / "t-000000500ms.jpg"
    different = tmp_path / "t-000001000ms.jpg"
    _base_image(original, quality=95)
    _base_image(recompressed, quality=50)
    image = Image.new("RGB", (128, 128), "white")
    draw = ImageDraw.Draw(image)
    draw.line((0, 0, 127, 127), fill="black", width=8)
    image.save(different)

    groups = find_duplicate_groups(
        [different, recompressed, original],
        max_hamming_distance=6,
    )

    assert len(groups) == 1
    assert groups[0].canonical == original
    assert tuple(groups[0].duplicates) == (recompressed,)


def test_rejects_negative_hamming_distance(tmp_path: Path) -> None:
    try:
        find_duplicate_groups([], max_hamming_distance=-1)
    except ValueError as error:
        assert "distance" in str(error)
    else:
        raise AssertionError("negative distance was accepted")
