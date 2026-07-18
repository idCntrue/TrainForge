from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import imagehash
from PIL import Image


@dataclass(frozen=True)
class DuplicateGroup:
    canonical: Path
    duplicates: Sequence[Path]


def find_duplicate_groups(
    image_paths: Sequence[Path],
    max_hamming_distance: int = 6,
) -> list[DuplicateGroup]:
    if max_hamming_distance < 0:
        raise ValueError("max_hamming_distance must not be negative")

    canonical_hashes: list[tuple[Path, imagehash.ImageHash]] = []
    grouped: dict[Path, list[Path]] = {}

    for path in sorted(image_paths):
        with Image.open(path) as image:
            perceptual_hash = imagehash.phash(image.convert("RGB"))

        matched_canonical: Path | None = None
        for canonical, canonical_hash in canonical_hashes:
            if perceptual_hash - canonical_hash <= max_hamming_distance:
                matched_canonical = canonical
                break

        if matched_canonical is None:
            canonical_hashes.append((path, perceptual_hash))
            grouped[path] = []
        else:
            grouped[matched_canonical].append(path)

    return [
        DuplicateGroup(canonical=canonical, duplicates=tuple(duplicates))
        for canonical, duplicates in grouped.items()
        if duplicates
    ]
