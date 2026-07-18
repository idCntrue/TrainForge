import pytest

from yolo_factory.datasets.split_planner import (
    InsufficientSplitGroups,
    InvalidSplitRatios,
    SampleRef,
    SplitRatios,
    plan_grouped_split,
)


def test_keeps_source_groups_together_and_is_deterministic() -> None:
    samples = [
        SampleRef("a1", "video-a"), SampleRef("a2", "video-a"),
        SampleRef("b1", "video-b"), SampleRef("c1", "video-c"),
        SampleRef("d1", "video-d"), SampleRef("e1", "video-e"),
    ]
    first = plan_grouped_split(samples, SplitRatios(50, 30, 20), seed=42)
    second = plan_grouped_split(list(reversed(samples)), SplitRatios(50, 30, 20), seed=42)

    assert first.assignments == second.assignments
    assert first.assignments["a1"] == first.assignments["a2"]
    assert set(first.assignments) == {sample.sample_id for sample in samples}
    assert sum(first.counts.values()) == len(samples)


@pytest.mark.parametrize("ratios", [SplitRatios(70, 20, 9), SplitRatios(-1, 91, 10)])
def test_rejects_invalid_ratios(ratios: SplitRatios) -> None:
    with pytest.raises(InvalidSplitRatios):
        plan_grouped_split([], ratios, seed=42)


def test_requires_one_independent_group_for_each_non_zero_split() -> None:
    samples = [SampleRef("a1", "video-a"), SampleRef("a2", "video-a")]
    with pytest.raises(InsufficientSplitGroups, match="3 independent source groups"):
        plan_grouped_split(samples, SplitRatios(70, 20, 10), seed=42)


def test_zero_percent_split_is_omitted() -> None:
    samples = [SampleRef(f"sample-{index}", f"source-{index}") for index in range(5)]
    plan = plan_grouped_split(samples, SplitRatios(80, 20, 0), seed=7)
    assert plan.counts["test"] == 0
    assert "test" not in set(plan.assignments.values())
