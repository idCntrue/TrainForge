import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Sample:
    sample_id: str
    source_video_id: str


@dataclass(frozen=True)
class DatasetSplit:
    train: tuple[str, ...]
    val: tuple[str, ...]
    test: tuple[str, ...]
    sources: tuple[tuple[str, str], ...]
    seed: int

    @property
    def all_ids(self) -> tuple[str, ...]:
        return self.train + self.val + self.test


def _group_samples(samples: Sequence[Sample]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for sample in sorted(samples, key=lambda item: item.sample_id):
        if sample.sample_id in seen:
            raise ValueError(f"duplicate sample ID: {sample.sample_id}")
        seen.add(sample.sample_id)
        groups[sample.source_video_id].append(sample.sample_id)
    return dict(groups)


def _flatten(
    group_ids: Sequence[str],
    groups: dict[str, list[str]],
) -> tuple[str, ...]:
    return tuple(
        sorted(sample_id for group_id in group_ids for sample_id in groups[group_id])
    )


def create_initial_split(
    samples: Sequence[Sample],
    seed: int = 42,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
) -> DatasetSplit:
    if not 0 < train_ratio < 1 or not 0 <= val_ratio < 1:
        raise ValueError("split ratios must be between 0 and 1")
    if train_ratio + val_ratio >= 1:
        raise ValueError("train and val ratios must leave a test split")
    groups = _group_samples(samples)
    group_ids = sorted(groups)
    random.Random(seed).shuffle(group_ids)
    group_count = len(group_ids)
    train_count = int(group_count * train_ratio)
    val_count = int(group_count * val_ratio)
    if group_count >= 3:
        train_count = max(1, train_count)
        val_count = max(1, val_count)
        if train_count + val_count >= group_count:
            train_count = group_count - val_count - 1
    train_groups = group_ids[:train_count]
    val_groups = group_ids[train_count : train_count + val_count]
    test_groups = group_ids[train_count + val_count :]
    sources = tuple(
        sorted(
            (sample_id, source_id)
            for source_id, sample_ids in groups.items()
            for sample_id in sample_ids
        )
    )
    return DatasetSplit(
        train=_flatten(train_groups, groups),
        val=_flatten(val_groups, groups),
        test=_flatten(test_groups, groups),
        sources=sources,
        seed=seed,
    )


def extend_split(
    previous: DatasetSplit,
    new_samples: Sequence[Sample],
    seed: int = 42,
) -> DatasetSplit:
    groups = _group_samples(new_samples)
    previous_sources = {source_id for _, source_id in previous.sources}
    overlap = previous_sources.intersection(groups)
    if overlap:
        raise ValueError(
            f"source video already exists in baseline: {sorted(overlap)[0]}"
        )
    previous_ids = set(previous.all_ids)
    duplicate_ids = previous_ids.intersection(
        sample_id for sample_ids in groups.values() for sample_id in sample_ids
    )
    if duplicate_ids:
        raise ValueError(f"sample already exists: {sorted(duplicate_ids)[0]}")

    group_ids = sorted(groups)
    random.Random(seed).shuffle(group_ids)
    val_count = int(len(group_ids) * 0.2)
    if len(group_ids) >= 2:
        val_count = max(1, val_count)
    train_groups = group_ids[: len(group_ids) - val_count]
    val_groups = group_ids[len(group_ids) - val_count :]
    new_sources = tuple(
        sorted(
            (sample_id, source_id)
            for source_id, sample_ids in groups.items()
            for sample_id in sample_ids
        )
    )
    return DatasetSplit(
        train=tuple(sorted(previous.train + _flatten(train_groups, groups))),
        val=tuple(sorted(previous.val + _flatten(val_groups, groups))),
        test=previous.test,
        sources=tuple(sorted(previous.sources + new_sources)),
        seed=previous.seed,
    )
