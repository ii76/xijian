from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models.opportunity import Opportunity
from models.signal_model import Signal
from services.llm_service import OpenAICompatibleClient


ROOT = Path(__file__).resolve().parents[1]
CLUSTER_PROMPT = (ROOT / "prompts" / "cluster_summary.txt").read_text(encoding="utf-8")

INSIGHT_TEMPLATES = {
    "代糖安全与甜味": "用户希望降低糖分负担，但仍需要可信的代糖安全边界和口感选择依据。",
    "控糖与血糖": "控糖人群关注零糖标识与真实血糖影响之间是否一致。",
    "减脂与热量": "减脂人群需要区分零糖、零卡与体重管理效果，避免把单一标签当作结论。",
    "配料与营养标签": "用户看到了配料表与营养成分表之间的信息差，需要一套可操作的读标方法。",
    "咖啡因与睡眠": "用户不仅关心糖，还需要按饮用时间识别咖啡因带来的睡眠代价。",
    "肠胃耐受": "肠胃敏感用户需要了解不同甜味剂和饮品配方的耐受差异。",
    "口腔健康": "无糖并不自动等于不伤牙，用户需要同时理解酸度与饮用习惯。",
    "特殊人群适用性": "孕期、儿童及特殊健康需求人群需要明确的适用边界和核验提示。",
    "产品横向对比": "用户需要以配料、甜味、热量与价格为共同标准进行横向选择。",
    "无糖饮料选择": "用户需要把抽象健康判断转化为具体、可执行的无糖饮料选择方法。",
}


def _generic_insight(topic: str) -> str:
    return f"用户围绕“{topic}”反复表达疑问、顾虑或选择需求，需要清晰、可核验的内容回应。"


def cluster_signals(
    signals: list[Signal],
    task_id: str,
    client: OpenAICompatibleClient | None = None,
    distance_threshold: float = 0.62,
) -> list[Opportunity]:
    if not signals:
        return []
    ordered_signals = sorted(signals, key=lambda item: (item.topic, item.comment_id, item.type))
    texts = [_signal_text(signal) for signal in ordered_signals]
    try:
        vectors = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1).fit_transform(texts)
        similarity = cosine_similarity(vectors)
        if len(ordered_signals) == 1:
            labels = np.array([0])
        else:
            labels = AgglomerativeClustering(
                n_clusters=None,
                metric="cosine",
                linkage="average",
                distance_threshold=distance_threshold,
            ).fit_predict(vectors.toarray())
    except Exception:
        labels = _keyword_labels(ordered_signals)
        similarity = np.equal.outer(labels, labels).astype(float)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        grouped[int(label)].append(index)

    cluster_items: list[tuple[str, list[int]]] = []
    for indexes in grouped.values():
        sort_key = min(
            f"{ordered_signals[index].topic}|{ordered_signals[index].comment_id}"
            for index in indexes
        )
        cluster_items.append((sort_key, indexes))
    cluster_items.sort(key=lambda item: item[0])

    opportunities: list[Opportunity] = []
    for opportunity_index, (_, indexes) in enumerate(cluster_items, start=1):
        cluster = [ordered_signals[index] for index in indexes]
        summary = _summarize_cluster(cluster, client)
        comment_ids = sorted({signal.comment_id for signal in cluster})
        signal_types = sorted({signal.type for signal in cluster})
        audiences = _top_values(signal.audience for signal in cluster)
        scenes = _top_values(signal.scene for signal in cluster)
        cohesion = _cluster_cohesion(similarity, indexes)
        dominant_type_count = Counter(signal.type for signal in cluster).most_common(1)[0][1]
        opportunities.append(
            Opportunity(
                id=f"OPP-{opportunity_index:03d}",
                task_id=task_id,
                name=summary["name"],
                insight=summary["insight"],
                signal_types=signal_types,
                comment_ids=comment_ids,
                audiences=audiences,
                scenes=scenes,
                tension_level=summary["tension_level"],
                emotion_level=summary["emotion_level"],
                audience_clarity=summary["audience_clarity"],
                content_convertibility=summary["content_convertibility"],
                signal_ids=sorted(signal.id for signal in cluster),
                cluster_cohesion=cohesion,
                label_consistency=dominant_type_count / len(cluster),
                weak_signal=len(comment_ids) <= 2,
            )
        )
    return opportunities


def _keyword_labels(signals: list[Signal]) -> np.ndarray:
    """Group by normalized topic when vectorization or clustering is unavailable."""
    labels: dict[str, int] = {}
    output = []
    for signal in signals:
        topic = "".join(str(signal.topic).casefold().split()) or "未分类"
        if topic not in labels:
            labels[topic] = len(labels)
        output.append(labels[topic])
    return np.asarray(output, dtype=int)


def comments_for_opportunity(opportunity: Opportunity | dict, comments: list[dict]) -> list[dict]:
    ids = set(opportunity.comment_ids if isinstance(opportunity, Opportunity) else opportunity["comment_ids"])
    return [comment for comment in comments if comment.get("id") in ids]


def _signal_text(signal: Signal) -> str:
    return signal.topic


def _cluster_cohesion(similarity: np.ndarray, indexes: list[int]) -> float:
    if len(indexes) <= 1:
        return 1.0
    values = [
        float(similarity[left, right])
        for position, left in enumerate(indexes)
        for right in indexes[position + 1 :]
    ]
    return round(sum(values) / len(values), 4) if values else 1.0


def _top_values(values, limit: int = 3) -> list[str]:
    counts = Counter(value for value in values if value)
    return [value for value, _ in counts.most_common(limit)]


def _summarize_cluster(
    cluster: list[Signal], client: OpenAICompatibleClient | None
) -> dict:
    if client is not None:
        payload = [
            {
                "comment_id": signal.comment_id,
                "type": signal.type,
                "topic": signal.topic,
                "need": signal.need,
                "concern": signal.concern,
                "audience": signal.audience,
                "scene": signal.scene,
                "emotion_level": signal.emotion_level,
            }
            for signal in cluster
        ]
        try:
            response = client.complete_json(
                CLUSTER_PROMPT, "请总结以下聚类：\n" + json.dumps(payload, ensure_ascii=False)
            )
            return _validate_summary(response)
        except Exception:
            pass
    return _fallback_summary(cluster)


def _validate_summary(response: dict) -> dict:
    name = str(response.get("name", "")).strip()
    insight = str(response.get("insight", "")).strip()
    if not name or not insight:
        raise ValueError("聚类总结缺少名称或洞察。")
    output = {"name": name[:40], "insight": insight[:240]}
    for key in (
        "tension_level",
        "emotion_level",
        "audience_clarity",
        "content_convertibility",
    ):
        output[key] = max(1, min(5, int(response[key])))
    return output


def _fallback_summary(cluster: list[Signal]) -> dict:
    topic = Counter(signal.topic for signal in cluster).most_common(1)[0][0]
    types = {signal.type for signal in cluster}
    emotion = max(1, min(5, round(sum(signal.emotion_level for signal in cluster) / len(cluster))))
    tension = 5 if "需求矛盾" in types else 4 if "观点分歧" in types else 3
    audience_count = len({signal.audience for signal in cluster if signal.audience})
    audience_clarity = 4 if audience_count == 1 else 3 if audience_count > 1 else 1
    convertibility = 5 if types.intersection({"对比需求", "高频疑问"}) else 4 if "隐藏场景" in types else 3
    name_prefix = "看懂" if "高频疑问" in types else "选择" if "对比需求" in types else "重新判断"
    return {
        "name": f"{name_prefix}{topic}",
        "insight": INSIGHT_TEMPLATES.get(topic, _generic_insight(topic)),
        "tension_level": tension,
        "emotion_level": emotion,
        "audience_clarity": audience_clarity,
        "content_convertibility": convertibility,
    }
