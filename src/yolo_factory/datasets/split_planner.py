from dataclasses import dataclass
from random import Random


SPLITS = ("train", "val", "test")


class InvalidSplitRatios(ValueError):
    pass


class InsufficientSplitGroups(ValueError):
    pass


@dataclass(frozen=True)
class SplitRatios:
    train: int
    val: int
    test: int

    def as_dict(self) -> dict[str, int]:
        return {"train": self.train, "val": self.val, "test": self.test}


@dataclass(frozen=True)
class SampleRef:
    sample_id: str
    source_group: str


@dataclass(frozen=True)
class SplitPlan:
    assignments: dict[str, str]
    requested_ratios: dict[str, int]
    counts: dict[str, int]
    actual_ratios: dict[str, float]
    seed: int

    def split_for(self, sample_id: str) -> str:
        return self.assignments[sample_id]


def plan_grouped_split(samples: list[SampleRef], ratios: SplitRatios, *, seed: int) -> SplitPlan:
    requested = ratios.as_dict()
    if any(value < 0 for value in requested.values()) or sum(requested.values()) != 100:
        raise InvalidSplitRatios("split ratios must be non-negative and total 100")

    groups: dict[str, list[str]] = {}
    for sample in samples:
        groups.setdefault(sample.source_group, []).append(sample.sample_id)
    active_splits = [split for split in SPLITS if requested[split] > 0]
    if len(groups) < len(active_splits):
        raise InsufficientSplitGroups(
            f"split requires at least {len(active_splits)} independent source groups; got {len(groups)}"
        )

    ordered_groups = [(key, sorted(value)) for key, value in sorted(groups.items())]
    Random(seed).shuffle(ordered_groups)
    counts = {split: 0 for split in SPLITS}
    assignments: dict[str, str] = {}
    total = len(samples)

    initial_splits = sorted(active_splits, key=lambda split: (-requested[split], SPLITS.index(split)))
    for (_, sample_ids), split in zip(ordered_groups[:len(initial_splits)], initial_splits):
        for sample_id in sample_ids:
            assignments[sample_id] = split
        counts[split] += len(sample_ids)

    for _, sample_ids in ordered_groups[len(initial_splits):]:
        split = max(
            active_splits,
            key=lambda candidate: (
                requested[candidate] / 100 * total - counts[candidate],
                requested[candidate],
                -SPLITS.index(candidate),
            ),
        )
        for sample_id in sample_ids:
            assignments[sample_id] = split
        counts[split] += len(sample_ids)

    actual = {
        split: round(counts[split] / total * 100, 2) if total else 0.0
        for split in SPLITS
    }
    return SplitPlan(assignments, requested, counts, actual, seed)
