from __future__ import annotations

import json
from time import perf_counter

import pytest

import app
from models.signal_model import Signal
from services.cluster_service import cluster_signals
from services.llm_service import LLMConfig, LLMError, LLMResponseError, OpenAICompatibleClient
from services.release_service import validate_release_state
from services.clean_service import clean_comments, normalize_text


def _demo_state() -> dict:
    clean = app.handle_clean(
        "无糖饮料", "食品饮料", ["科普", "测评"], [], "", "comment", app.load_demo_payload()
    )
    return app.handle_demo_precomputed(clean[5], clean[4])[5]


def test_model_timeout_is_bounded_by_retry_limit() -> None:
    calls = []

    def transport(*args):
        calls.append(1)
        raise LLMError("timeout")

    client = OpenAICompatibleClient(LLMConfig(api_key="test", max_retries=1), transport)
    with pytest.raises(LLMResponseError, match="重试后仍不可用"):
        client.complete_json("system", "user")
    assert len(calls) == 2


def test_embedding_or_clustering_failure_uses_keyword_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.cluster_service.TfidfVectorizer.fit_transform",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("embedding unavailable")),
    )
    signals = [
        Signal(comment_id="C-1", type="高频疑问", topic="代糖安全"),
        Signal(comment_id="C-2", type="需求矛盾", topic="代糖安全"),
        Signal(comment_id="C-3", type="高频疑问", topic="咖啡因睡眠"),
    ]
    opportunities = cluster_signals(signals, "T-FALLBACK")
    assert len(opportunities) == 2
    assert sorted(len(item.comment_ids) for item in opportunities) == [1, 2]


def test_release_metrics_are_fully_traceable_and_program_calculated() -> None:
    metrics = validate_release_state(_demo_state())
    assert metrics["formal_opportunities"] >= 3
    assert metrics["traceability_rate"] == 1.0
    assert metrics["numeric_program_rate"] == 1.0
    assert metrics["brief_evidence_rate"] == 1.0


def test_api_key_is_not_exposed_by_service_notice(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "secret-key-must-not-leak")
    notice = app._ai_service_notice(_demo_state())
    assert "secret-key-must-not-leak" not in notice


def test_precomputed_files_are_valid_json() -> None:
    for path in (app.ROOT / "data" / "demo").glob("*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))


def test_500_comment_cleaning_stays_below_five_seconds() -> None:
    raw = [{"text": f"第{index}条评论：无糖饮料为什么还是甜的？"} for index in range(500)]
    started = perf_counter()
    comments, summary = clean_comments(raw, "T-PERF")
    assert perf_counter() - started < 5
    assert len(comments) == 500
    assert summary.valid_count == 500


def test_html_script_and_formula_text_remain_inert() -> None:
    cleaned = normalize_text('<script>alert("x")</script><b>=HYPERLINK("bad")</b>')
    assert "<script" not in cleaned
    assert "<b>" not in cleaned
    assert "alert" in cleaned
    assert "HYPERLINK" in cleaned
