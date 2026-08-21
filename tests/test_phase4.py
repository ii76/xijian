from __future__ import annotations

import json
import sqlite3
import time

import app
from services.brief_service import FORBIDDEN_CLAIMS, generate_briefs, regenerate_brief
from services.export_service import build_markdown_report, cleanup_temp_files, export_markdown
from services.storage_service import load_briefs, load_latest_analysis, save_analysis, save_briefs
from services.view_service import filter_opportunities


def _demo_state() -> dict:
    clean_result = app.handle_clean(
        "无糖饮料",
        "食品饮料",
        ["科普", "测评"],
        [],
        "",
        "comment",
        app.load_demo_payload(),
    )
    return app.handle_demo_precomputed(clean_result[5], clean_result[4])[5]


def test_each_opportunity_generates_three_distinct_complete_briefs() -> None:
    state = _demo_state()
    formal, _ = filter_opportunities(state["opportunities"])
    opportunity = formal[0]
    briefs = generate_briefs(opportunity["id"], state)
    assert len(briefs) == 3
    assert len({item["strategy"] for item in briefs}) == 3
    assert len({item["angle"] for item in briefs}) == 3
    assert len({tuple(item["structure"]) for item in briefs}) == 3
    allowed_ids = set(opportunity["comment_ids"])
    for item in briefs:
        assert 3 <= len(item["structure"]) <= 5
        assert len(item["evidence_comment_ids"]) >= 3
        assert set(item["evidence_comment_ids"]).issubset(allowed_ids)
        assert item["opportunity_id"] == opportunity["id"]
        assert "核验" in item["risk_notice"]
        assert not any(claim in json.dumps(item, ensure_ascii=False) for claim in FORBIDDEN_CLAIMS)


def test_regeneration_only_replaces_selected_brief() -> None:
    state = _demo_state()
    opportunity = filter_opportunities(state["opportunities"])[0][0]
    original = generate_briefs(opportunity["id"], state)
    updated = regenerate_brief(opportunity["id"], state, original, 1)
    assert updated[0] == original[0]
    assert updated[2] == original[2]
    assert updated[1]["id"] != original[1]["id"]
    assert updated[1]["version"] > original[1]["version"]


def test_sqlite_saves_all_analysis_entities_and_restores_snapshot(tmp_path) -> None:
    state = _demo_state()
    path = tmp_path / "xijian.db"
    save_analysis(state, path)
    opportunity = filter_opportunities(state["opportunities"])[0][0]
    briefs = generate_briefs(opportunity["id"], state)
    save_briefs(state["task"]["id"], opportunity["id"], briefs, path)
    restored = load_latest_analysis(path)
    assert restored["task"]["id"] == state["task"]["id"]
    assert len(restored["comments"]) == len(state["comments"])
    assert load_briefs(state["task"]["id"], opportunity["id"], path) == briefs
    with sqlite3.connect(path) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("tasks", "comments", "signals", "opportunities", "briefs")
        }
    assert counts["tasks"] == 1
    assert counts["comments"] == len(state["comments"])
    assert counts["signals"] == len(state["signals"])
    assert counts["opportunities"] == len(state["opportunities"])
    assert counts["briefs"] == 3


def test_markdown_export_contains_structure_and_real_evidence(tmp_path) -> None:
    state = _demo_state()
    opportunity = filter_opportunities(state["opportunities"])[0][0]
    briefs = generate_briefs(opportunity["id"], state)
    report = build_markdown_report(state, briefs)
    assert "## 1. 数据概览" in report
    assert "## 4. 内容 Brief" in report
    assert "## 5. 评论证据" in report
    assert briefs[0]["title"] in report
    assert briefs[0]["evidence_comments"][0]["content"] in report
    path = export_markdown(state, briefs, tmp_path)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == report


def test_cleanup_limits_export_accumulation(tmp_path) -> None:
    stale = tmp_path / "xijian-stale.md"
    stale.write_text("old", encoding="utf-8")
    old = time.time() - 100
    stale.touch()
    import os
    os.utime(stale, (old, old))
    assert cleanup_temp_files(tmp_path, max_age_seconds=10, keep=20) == 1
    assert not stale.exists()


def test_demo_has_pre_generated_briefs() -> None:
    payload = app.load_demo_briefs()
    assert len(payload) >= 3
    assert all(len(briefs) == 3 for briefs in payload.values())
