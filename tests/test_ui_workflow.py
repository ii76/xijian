from time import perf_counter

import app
from services.import_service import parse_pasted_text
from services.clean_service import clean_comments
from services.cluster_service import cluster_signals
from services.score_service import score_opportunities
from services.signal_service import analyze_comments
from services.view_service import filter_opportunities


def _cleaned_demo():
    payload = app.load_demo_payload()
    result = app.handle_clean(
        "无糖饮料", "食品饮料", ["科普", "测评"], [], "", "comment", payload
    )
    return result[5], result[4]


def test_six_step_analysis_finishes_with_completed_task(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    clean_state, task_state = _cleaned_demo()
    updates = list(app.handle_analysis(clean_state, task_state))
    assert len(updates) == 5
    assert "分析完成" in updates[-1][0]
    assert updates[-1][5]["task"]["status"] == "completed"
    assert all(f"{step} " in updates[-1][1] for step in range(1, 7))


def test_precomputed_demo_can_be_loaded_without_reanalysis() -> None:
    clean_state, task_state = _cleaned_demo()
    result = app.handle_demo_precomputed(clean_state, task_state)
    state = result[5]
    assert state["mode"] == "precomputed_demo"
    assert len(state["signals"]) == 69
    assert len(state["opportunities"]) == 10
    assert state["task"]["status"] == "completed"


def test_uploaded_file_cannot_load_precomputed_demo() -> None:
    payload = parse_pasted_text("\n".join(f"第{i}条：这款相机续航怎么样？" for i in range(20)))
    clean_result = app.handle_clean(
        "无糖饮料", "数码家电", ["测评"], [], "", "comment", payload
    )
    result = app.handle_demo_precomputed(clean_result[5], clean_result[4])
    assert "不是内置示例" in result[0]
    assert result[5] == {}


def test_custom_topic_drives_local_fallback_results(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    payload = parse_pasted_text(
        "\n".join(
            [
                "这款轻薄本续航真的能撑一天吗？",
                "学生党预算有限，但又怕性能不够怎么办？",
                "办公本和游戏本到底应该怎么选？",
            ]
            * 7
        )
    )
    clean_result = app.handle_clean(
        "轻薄笔记本", "数码家电", ["测评"], [], "学生党", "comment", payload
    )
    state = list(app.handle_analysis(clean_result[5], clean_result[4]))[-1][5]
    assert state["task"]["topic"] == "轻薄笔记本"
    assert state["mode"] == "local_fallback"
    assert state["signals"]
    combined = " ".join(
        [signal["topic"] for signal in state["signals"]]
        + [item["name"] + item["insight"] for item in state["opportunities"]]
    )
    assert "轻薄笔记本" in combined
    assert "无糖饮料" not in combined


def test_formal_opportunities_have_three_evidence_comments(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    clean_state, task_state = _cleaned_demo()
    state = list(app.handle_analysis(clean_state, task_state))[-1][5]
    formal, weak = filter_opportunities(state["opportunities"])
    assert len(formal) >= 3
    assert all(item["comment_count"] >= 3 for item in formal)
    assert weak


def test_brief_selection_carries_current_opportunity_id(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    clean_state, task_state = _cleaned_demo()
    state = list(app.handle_analysis(clean_state, task_state))[-1][5]
    formal, _ = filter_opportunities(state["opportunities"])
    opportunity_id, message, _ = app._select_brief(formal[0]["id"], state)
    assert opportunity_id == formal[0]["id"]
    assert opportunity_id in message


def test_500_comment_analysis_stays_within_ninety_seconds(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    raw = [
        {"text": f"第{index}条评论：无糖饮料为什么还是甜的？"}
        for index in range(500)
    ]
    comments, summary = clean_comments(raw, "T-500")
    comment_dicts = [comment.to_dict() for comment in comments]
    started = perf_counter()
    analysis = analyze_comments(comment_dicts)
    opportunities = score_opportunities(
        cluster_signals(analysis.signals, "T-500"), comment_dicts
    )
    assert perf_counter() - started < 90
    assert summary.valid_count == 500
    assert opportunities
