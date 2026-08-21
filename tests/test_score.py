from models.opportunity import Opportunity
from services.score_service import (
    calculate_gap_score,
    confidence_for_opportunity,
    map_level,
    priority_for_score,
    score_opportunities,
)


def _opportunity(comment_ids: list[str]) -> Opportunity:
    return Opportunity(
        id="OPP-001",
        task_id="T-TEST",
        name="代糖安全",
        insight="用户需要安全边界。",
        signal_types=["高频疑问"],
        comment_ids=comment_ids,
        audiences=["控糖人群"],
        scenes=[],
        tension_level=5,
        emotion_level=5,
        audience_clarity=5,
        content_convertibility=5,
        cluster_cohesion=0.9,
        label_consistency=0.8,
    )


def test_level_mapping() -> None:
    assert [map_level(level) for level in range(1, 6)] == [20, 40, 60, 80, 100]


def test_gap_score_can_be_recalculated() -> None:
    score, detail = calculate_gap_score(0.10, 5, 5, 5, 5)
    assert detail["coverage"]["score"] == 50
    assert score == 85


def test_gap_score_is_bounded() -> None:
    assert 0 <= calculate_gap_score(-3, 1, 1, 1, 1)[0] <= 100
    assert 0 <= calculate_gap_score(9, 5, 5, 5, 5)[0] <= 100


def test_priority_boundaries() -> None:
    assert priority_for_score(80) == "优先策划"
    assert priority_for_score(60) == "值得关注"
    assert priority_for_score(59) == "补充观察"


def test_low_sample_is_low_confidence() -> None:
    assert confidence_for_opportunity(2, 1.0, 1.0) == "低"


def test_duplicate_comment_ids_are_counted_once() -> None:
    comments = [{"id": f"C-{index:04d}", "valid": True} for index in range(1, 11)]
    scored = score_opportunities([_opportunity(["C-0001", "C-0001", "C-0002"])], comments)[0]
    assert scored.comment_count == 2
    assert scored.coverage_rate == 0.2


def test_scoring_is_deterministic_and_separate_from_confidence() -> None:
    comments = [{"id": f"C-{index:04d}", "valid": True} for index in range(1, 11)]
    opportunity = _opportunity(["C-0001"])
    first = score_opportunities([opportunity], comments)[0]
    second = score_opportunities([opportunity], comments)[0]
    assert first.to_dict() == second.to_dict()
    assert first.gap_score == 85
    assert first.confidence == "低"
