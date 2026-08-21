from __future__ import annotations

import html
from collections import Counter


SORT_OPTIONS = ("隙值从高到低", "评论数从高到低")
EVIDENCE_FILTERS = ("全部证据", "强表达", "高频疑问", "不同观点", "高赞评论")


def filter_opportunities(
    opportunities: list[dict],
    sort_by: str = "隙值从高到低",
    signal_types: list[str] | None = None,
    priority: str = "全部优先级",
) -> tuple[list[dict], list[dict]]:
    formal = [item for item in opportunities if int(item.get("comment_count", 0)) >= 3]
    weak = [item for item in opportunities if int(item.get("comment_count", 0)) < 3]
    if signal_types:
        selected = set(signal_types)
        formal = [item for item in formal if selected.intersection(item.get("signal_types", []))]
    if priority and priority != "全部优先级":
        formal = [item for item in formal if item.get("priority") == priority]
    if sort_by == "评论数从高到低":
        formal.sort(key=lambda item: (-item["comment_count"], -item["gap_score"], item["id"]))
    else:
        formal.sort(key=lambda item: (-item["gap_score"], -item["comment_count"], item["id"]))
    weak.sort(key=lambda item: (-item["gap_score"], item["id"]))
    return formal, weak


def render_overview_summary(state: dict, formal_count: int, weak_count: int) -> str:
    task = state.get("task", {})
    quality = state.get("quality", {})
    mode = {
        "llm": "在线大模型",
        "precomputed_demo": "示例预计算结果",
        "local_fallback": "本地确定性分析",
    }.get(state.get("mode"), state.get("mode", "未知模式"))
    return f"""
<div class="overview-heading">
  <div>
    <div class="eyebrow">调研主题</div>
    <h2>{html.escape(str(task.get("topic", "未命名调研")))}</h2>
    <p>{html.escape(str(task.get("industry", "")))} · {html.escape(mode)}</p>
  </div>
  <div class="metric-strip">
    <span><b>{quality.get("raw_count", 0)}</b> 原始</span>
    <span><b>{quality.get("unique_count", 0)}</b> 去重</span>
    <span><b>{quality.get("valid_count", 0)}</b> 有效</span>
    <span><b>{formal_count}</b> 机会</span>
    <span><b>{weak_count}</b> 弱信号</span>
  </div>
</div>
"""


def render_signal_distribution(signals: list[dict]) -> str:
    signal_types = ("需求矛盾", "高频疑问", "观点分歧", "对比需求", "隐藏场景")
    counts = Counter(signal["type"] for signal in signals)
    maximum = max(counts.values(), default=1)
    rows = []
    for signal_type in signal_types:
        count = counts[signal_type]
        width = max(4, round(count / maximum * 100)) if count else 0
        rows.append(
            f'<div class="signal-row"><span>{signal_type}</span>'
            f'<i style="width:{width}%"></i><b>{count}</b></div>'
        )
    return '<div class="signal-panel"><div class="eyebrow">五类内容信号</div>' + "".join(rows) + "</div>"


def render_weak_signals(weak: list[dict]) -> str:
    if not weak:
        return ""
    items = "".join(
        f"<li><b>{html.escape(item['name'])}</b><span>{item['comment_count']} 条证据 · "
        f"隙值 {item['gap_score']} · 低可信度</span></li>"
        for item in weak
    )
    return f"""
<details class="weak-signals">
  <summary>低频弱信号 {len(weak)} 项</summary>
  <ul>{items}</ul>
</details>
"""


def render_opportunity_card(opportunity: dict, comments: list[dict]) -> str:
    comment_by_id = {comment["id"]: comment for comment in comments}
    evidence = [comment_by_id[item] for item in opportunity["comment_ids"] if item in comment_by_id]
    typical = max(evidence, key=lambda item: item.get("like_count", 0), default={})
    audience = "、".join(opportunity.get("audiences", [])) or "待进一步识别"
    types = " / ".join(opportunity.get("signal_types", []))
    return f"""
<div class="opp-card">
  <div class="opp-score"><b>{opportunity['gap_score']}</b><span>隙值</span></div>
  <div class="opp-body">
    <div class="opp-meta"><span>{html.escape(opportunity['priority'])}</span>
      <span>可信度 {html.escape(opportunity['confidence'])}</span></div>
    <h3>{html.escape(opportunity['name'])}</h3>
    <p class="opp-insight">{html.escape(opportunity['insight'])}</p>
    <div class="opp-facts">
      <span>{opportunity['comment_count']} 条评论</span>
      <span>覆盖率 {opportunity['coverage_rate']:.1%}</span>
      <span>{html.escape(types)}</span>
    </div>
    <p><b>核心人群：</b>{html.escape(audience)}</p>
    <blockquote>{html.escape(str(typical.get("content", "暂无典型评论")))}</blockquote>
  </div>
</div>
"""


def build_detail(opportunity_id: str, state: dict, evidence_filter: str = "全部证据") -> dict:
    opportunity = next(
        (item for item in state.get("opportunities", []) if item["id"] == opportunity_id),
        None,
    )
    if opportunity is None:
        raise ValueError("内容机会不存在。")
    signal_ids = set(opportunity.get("signal_ids", []))
    signals = [
        signal for signal in state.get("signals", [])
        if signal["id"] in signal_ids
        or (not signal_ids and signal["comment_id"] in opportunity["comment_ids"])
    ]
    signals_by_comment: dict[str, list[dict]] = {}
    for signal in signals:
        signals_by_comment.setdefault(signal["comment_id"], []).append(signal)
    comments = [
        comment for comment in state.get("comments", [])
        if comment["id"] in set(opportunity["comment_ids"])
    ]
    evidence = [_evidence_item(comment, signals_by_comment.get(comment["id"], [])) for comment in comments]
    evidence = filter_evidence(evidence, evidence_filter)
    needs = _top_text(signal.get("need", "") for signal in signals)
    concerns = _top_text(signal.get("concern", "") for signal in signals)
    return {
        "opportunity": opportunity,
        "signals": signals,
        "needs": needs,
        "concerns": concerns,
        "evidence": evidence,
    }


def filter_evidence(evidence: list[dict], evidence_filter: str) -> list[dict]:
    if evidence_filter == "强表达":
        output = [item for item in evidence if item["emotion_level"] >= 4]
    elif evidence_filter == "高频疑问":
        output = [item for item in evidence if "高频疑问" in item["signal_types"]]
    elif evidence_filter == "不同观点":
        output = [item for item in evidence if "观点分歧" in item["signal_types"]]
    elif evidence_filter == "高赞评论":
        output = [item for item in evidence if item["like_count"] >= 20]
    else:
        output = list(evidence)
    return sorted(output, key=lambda item: (-item["like_count"], item["comment_id"]))


def render_detail_header(detail: dict) -> str:
    item = detail["opportunity"]
    return f"""
<div class="detail-heading">
  <div><div class="eyebrow">{html.escape(item['priority'])} · 可信度 {html.escape(item['confidence'])}</div>
  <h2>{html.escape(item['name'])}</h2><p>{html.escape(item['insight'])}</p></div>
  <div class="detail-score"><b>{item['gap_score']}</b><span>隙值</span></div>
</div>
"""


def render_score_detail(detail: dict) -> str:
    item = detail["opportunity"]
    score = item["score_detail"]
    rows = (
        ("讨论覆盖度", score["coverage"]["score"], score["coverage"]["explanation"]),
        ("需求张力", score["tension"]["score"], score["tension"]["explanation"]),
        ("情绪强度", score["emotion"]["score"], score["emotion"]["explanation"]),
        ("人群清晰度", score["audience"]["score"], score["audience"]["explanation"]),
        ("内容转化度", score["convertibility"]["score"], score["convertibility"]["explanation"]),
    )
    body = "".join(
        f"<tr><th>{name}</th><td><b>{value:g}</b></td><td>{html.escape(explanation)}</td></tr>"
        for name, value, explanation in rows
    )
    return f'<table class="score-table"><tbody>{body}</tbody></table>'


def render_detail_insight(detail: dict) -> str:
    item = detail["opportunity"]
    audiences = "、".join(item.get("audiences", [])) or "待识别"
    scenes = "、".join(item.get("scenes", [])) or "通用消费场景"
    return f"""
<div class="insight-grid">
  <section><div class="eyebrow">用户期待</div><p>{html.escape(detail['needs'] or '获得清晰、可执行的选择依据')}</p></section>
  <section><div class="eyebrow">用户顾虑</div><p>{html.escape(detail['concerns'] or '现有内容没有充分回应风险与边界')}</p></section>
  <section><div class="eyebrow">内容缺口</div><p>{html.escape(item['insight'])}</p></section>
  <section><div class="eyebrow">人群与场景</div><p>{html.escape(audiences)} · {html.escape(scenes)}</p></section>
</div>
"""


def render_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return '<div class="empty-state">当前筛选下没有证据，请切换筛选条件。</div>'
    cards = []
    for item in evidence:
        tags = " / ".join(item["signal_types"]) or "关联评论"
        cards.append(
            f"""
<article class="evidence-item">
  <div class="evidence-meta"><b>{html.escape(item['comment_id'])}</b>
    <span>{html.escape(tags)}</span><span>{html.escape(item['source_platform'])} · {item['like_count']} 赞</span></div>
  <p>{html.escape(item['content'])}</p>
  <small>{html.escape(item['reason'])}</small>
</article>
"""
        )
    return "".join(cards)


def _evidence_item(comment: dict, signals: list[dict]) -> dict:
    types = sorted({signal["type"] for signal in signals})
    topics = sorted({signal["topic"] for signal in signals})
    needs = _top_text(signal.get("need", "") for signal in signals)
    concerns = _top_text(signal.get("concern", "") for signal in signals)
    if needs and concerns:
        reason = f"表达了“{needs}”，同时提到“{concerns}”。"
    elif topics:
        reason = f"直接涉及{'、'.join(topics[:2])}。"
    else:
        reason = "该评论是当前机会的直接原始证据。"
    return {
        "comment_id": comment["id"],
        "content": comment["content"],
        "source_platform": comment.get("source_platform", "unknown"),
        "like_count": int(comment.get("like_count", 0) or 0),
        "signal_types": types,
        "topics": topics,
        "emotion_level": max((int(signal.get("emotion_level", 1)) for signal in signals), default=1),
        "reason": reason,
    }


def _top_text(values) -> str:
    counts = Counter(value for value in values if value)
    return counts.most_common(1)[0][0] if counts else ""
