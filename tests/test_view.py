from services.view_service import (
    build_detail,
    filter_evidence,
    filter_opportunities,
    render_evidence,
)


def _opportunity(
    opportunity_id: str,
    score: int,
    count: int,
    signal_types: list[str],
    priority: str,
) -> dict:
    return {
        "id": opportunity_id,
        "gap_score": score,
        "comment_count": count,
        "signal_types": signal_types,
        "priority": priority,
    }


def test_filter_separates_weak_signals_and_sorts_by_score() -> None:
    opportunities = [
        _opportunity("OPP-1", 70, 5, ["高频疑问"], "值得关注"),
        _opportunity("OPP-2", 88, 4, ["需求矛盾"], "优先策划"),
        _opportunity("OPP-3", 59, 2, ["隐藏场景"], "补充观察"),
    ]
    formal, weak = filter_opportunities(opportunities)
    assert [item["id"] for item in formal] == ["OPP-2", "OPP-1"]
    assert [item["id"] for item in weak] == ["OPP-3"]


def test_filter_supports_comment_sort_signal_and_priority() -> None:
    opportunities = [
        _opportunity("OPP-1", 90, 3, ["需求矛盾"], "优先策划"),
        _opportunity("OPP-2", 70, 8, ["高频疑问"], "值得关注"),
        _opportunity("OPP-3", 65, 6, ["需求矛盾", "高频疑问"], "值得关注"),
    ]
    sorted_items, _ = filter_opportunities(opportunities, "评论数从高到低")
    assert [item["id"] for item in sorted_items] == ["OPP-2", "OPP-3", "OPP-1"]
    filtered, _ = filter_opportunities(
        opportunities,
        signal_types=["需求矛盾"],
        priority="值得关注",
    )
    assert [item["id"] for item in filtered] == ["OPP-3"]


def test_evidence_filters_are_deterministic() -> None:
    evidence = [
        {
            "comment_id": "C-1",
            "emotion_level": 4,
            "signal_types": ["高频疑问"],
            "like_count": 5,
        },
        {
            "comment_id": "C-2",
            "emotion_level": 2,
            "signal_types": ["观点分歧"],
            "like_count": 30,
        },
    ]
    assert [item["comment_id"] for item in filter_evidence(evidence, "强表达")] == ["C-1"]
    assert [item["comment_id"] for item in filter_evidence(evidence, "不同观点")] == ["C-2"]
    assert [item["comment_id"] for item in filter_evidence(evidence, "高赞评论")] == ["C-2"]


def test_rendered_evidence_escapes_untrusted_html() -> None:
    html = render_evidence(
        [
            {
                "comment_id": "C-1",
                "content": "<script>alert(1)</script>",
                "source_platform": "demo",
                "like_count": 2,
                "signal_types": ["高频疑问"],
                "reason": "直接证据",
            }
        ]
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_detail_only_uses_real_bound_comments() -> None:
    state = {
        "opportunities": [
            {
                "id": "OPP-1",
                "comment_ids": ["C-1", "C-2", "C-3"],
                "signal_ids": ["S-1", "S-2", "S-3"],
                "audiences": ["控糖人群"],
                "scenes": [],
                "insight": "需要解释",
            }
        ],
        "signals": [
            {
                "id": f"S-{index}",
                "comment_id": f"C-{index}",
                "type": "高频疑问",
                "topic": "代糖安全",
                "need": "需要解释",
                "concern": "担心风险",
                "emotion_level": 3,
            }
            for index in range(1, 4)
        ],
        "comments": [
            {
                "id": f"C-{index}",
                "content": f"评论 {index}",
                "source_platform": "demo",
                "like_count": index,
            }
            for index in range(1, 5)
        ],
    }
    detail = build_detail("OPP-1", state)
    assert {item["comment_id"] for item in detail["evidence"]} == {"C-1", "C-2", "C-3"}
    assert len(detail["evidence"]) == 3

