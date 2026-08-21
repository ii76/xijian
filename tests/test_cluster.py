from models.signal_model import Signal
from services.clean_service import clean_comments
from services.cluster_service import cluster_signals, comments_for_opportunity
from services.import_service import inspect_file, materialize_records
from services.score_service import score_opportunities
from services.signal_service import analyze_comments


def _demo_pipeline():
    raw = materialize_records(inspect_file("data/demo/sugar_free_comments.csv"))
    comments, _ = clean_comments(raw, "T-DEMO")
    comment_dicts = [comment.to_dict() for comment in comments]
    analysis = analyze_comments(comment_dicts)
    opportunities = score_opportunities(
        cluster_signals(analysis.signals, "T-DEMO"), comment_dicts
    )
    return comment_dicts, analysis, opportunities


def test_demo_generates_at_least_five_candidates(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    comments, analysis, opportunities = _demo_pipeline()
    valid_ids = {comment["id"] for comment in comments if comment["valid"]}
    assert len(opportunities) >= 5
    assert len([item for item in opportunities if item.comment_count > 0]) >= 3
    assert len({item.name for item in opportunities}) == len(opportunities)
    assert all(set(item.comment_ids).issubset(valid_ids) for item in opportunities)
    assert all(len(item.comment_ids) == len(set(item.comment_ids)) for item in opportunities)


def test_opportunity_can_retrieve_original_comments(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    comments, _, opportunities = _demo_pipeline()
    evidence = comments_for_opportunity(opportunities[0], comments)
    assert {item["id"] for item in evidence} == set(opportunities[0].comment_ids)


def test_single_signal_is_preserved_as_low_frequency_opportunity() -> None:
    signal = Signal(
        id="SIG-1",
        comment_id="C-0001",
        type="隐藏场景",
        topic="夜间加班",
        scene="晚间加班",
        emotion_level=2,
        evidence_span="晚上加班想喝无糖饮料",
    )
    opportunity = cluster_signals([signal], "T-TEST")[0]
    assert opportunity.comment_ids == ["C-0001"]
    assert opportunity.weak_signal is True


def test_other_signals_are_kept_when_no_tension_exists(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    comments = [{"id": "C-0001", "content": "无糖饮料为什么还是甜的？", "valid": True}]
    analysis = analyze_comments(comments)
    assert "高频疑问" in {signal.type for signal in analysis.signals}
    assert "需求矛盾" not in {signal.type for signal in analysis.signals}
    assert cluster_signals(analysis.signals, "T-TEST")


def test_full_opportunity_pipeline_is_deterministic(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    comments, _, first = _demo_pipeline()
    analysis = analyze_comments(comments)
    second = score_opportunities(cluster_signals(analysis.signals, "T-DEMO"), comments)
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
