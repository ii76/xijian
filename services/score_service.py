from __future__ import annotations

from copy import deepcopy

from models.opportunity import Opportunity


LEVEL_MAP = {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}


def map_level(level: int) -> int:
    if level not in LEVEL_MAP:
        raise ValueError("评分等级必须为 1-5。")
    return LEVEL_MAP[level]


def calculate_gap_score(
    coverage_rate: float,
    tension_level: int,
    emotion_level: int,
    audience_clarity: int,
    content_convertibility: int,
) -> tuple[int, dict]:
    coverage_rate = max(0.0, min(1.0, float(coverage_rate)))
    coverage_score = min(100.0, coverage_rate / 0.20 * 100.0)
    tension = map_level(tension_level)
    emotion = map_level(emotion_level)
    audience = map_level(audience_clarity)
    convertibility = map_level(content_convertibility)
    gap_score = round(
        0.30 * coverage_score
        + 0.25 * tension
        + 0.15 * emotion
        + 0.15 * audience
        + 0.15 * convertibility
    )
    detail = {
        "coverage": {
            "score": round(coverage_score, 2),
            "weight": 0.30,
            "explanation": "由机会唯一评论数除以有效评论总数计算。",
        },
        "tension": {"level": tension_level, "score": tension, "weight": 0.25, "explanation": "需求期待与顾虑的冲突程度。"},
        "emotion": {"level": emotion_level, "score": emotion, "weight": 0.15, "explanation": "评论表达的迫切、质疑或强烈程度。"},
        "audience": {"level": audience_clarity, "score": audience, "weight": 0.15, "explanation": "目标人群是否清晰可识别。"},
        "convertibility": {"level": content_convertibility, "score": convertibility, "weight": 0.15, "explanation": "机会转化为具体内容方案的难易度。"},
    }
    return max(0, min(100, gap_score)), detail


def priority_for_score(score: int) -> str:
    if score >= 80:
        return "优先策划"
    if score >= 60:
        return "值得关注"
    return "补充观察"


def confidence_for_opportunity(
    comment_count: int, cluster_cohesion: float, label_consistency: float
) -> str:
    if comment_count <= 2:
        return "低"
    if comment_count >= 5 and cluster_cohesion >= 0.60 and label_consistency >= 0.35:
        return "高"
    if comment_count >= 3 and cluster_cohesion >= 0.40:
        return "中"
    return "低"


def score_opportunities(
    opportunities: list[Opportunity], comments: list[dict]
) -> list[Opportunity]:
    valid_ids = {str(comment["id"]) for comment in comments if comment.get("valid", True)}
    valid_total = len(valid_ids)
    scored: list[Opportunity] = []
    for opportunity in opportunities:
        item = deepcopy(opportunity)
        unique_ids = sorted(set(item.comment_ids).intersection(valid_ids))
        item.comment_ids = unique_ids
        item.comment_count = len(unique_ids)
        item.coverage_rate = item.comment_count / valid_total if valid_total else 0.0
        item.gap_score, item.score_detail = calculate_gap_score(
            item.coverage_rate,
            item.tension_level,
            item.emotion_level,
            item.audience_clarity,
            item.content_convertibility,
        )
        item.priority = priority_for_score(item.gap_score)
        item.confidence = confidence_for_opportunity(
            item.comment_count, item.cluster_cohesion, item.label_consistency
        )
        item.weak_signal = item.comment_count <= 2
        scored.append(item)
    return sorted(scored, key=lambda item: (-item.gap_score, -item.comment_count, item.id))
