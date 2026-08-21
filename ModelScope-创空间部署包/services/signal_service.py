from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from models.signal_model import SIGNAL_TYPES, Signal
from services.llm_service import LLMConfigurationError, LLMResponseError, OpenAICompatibleClient


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT = (ROOT / "prompts" / "comment_analysis.txt").read_text(encoding="utf-8")
FORBIDDEN_OUTPUT_KEYS = {
    "comment_count",
    "total_comments",
    "coverage_rate",
    "coverage",
    "gap_score",
    "priority",
    "confidence",
}


@dataclass(slots=True)
class FailedBatch:
    batch_index: int
    comment_ids: list[str]
    error: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SignalAnalysisResult:
    signals: list[Signal]
    processed_comment_ids: list[str]
    failed_batches: list[FailedBatch]
    mode: str

    def to_dict(self) -> dict:
        return {
            "signals": [signal.to_dict() for signal in self.signals],
            "processed_comment_ids": self.processed_comment_ids,
            "failed_batches": [batch.to_dict() for batch in self.failed_batches],
            "mode": self.mode,
        }


def analyze_comments(
    comments: list[dict],
    client: OpenAICompatibleClient | None = None,
    batch_size: int = 40,
    batch_indexes: set[int] | None = None,
    topic_hint: str = "",
) -> SignalAnalysisResult:
    if not 30 <= batch_size <= 60:
        raise ValueError("batch_size 必须位于 30-60。")
    valid_comments = [comment for comment in comments if comment.get("valid", True)]
    batches = [valid_comments[index : index + batch_size] for index in range(0, len(valid_comments), batch_size)]

    mode = "llm"
    if client is None:
        try:
            client = OpenAICompatibleClient.from_env()
        except LLMConfigurationError:
            mode = "local_fallback"

    signals: list[Signal] = []
    processed: list[str] = []
    failed: list[FailedBatch] = []
    for batch_index, batch in enumerate(batches):
        if batch_indexes is not None and batch_index not in batch_indexes:
            continue
        try:
            batch_signals = (
                _analyze_model_batch(batch, client)
                if mode == "llm" and client is not None
                else _analyze_local_batch(batch, topic_hint)
            )
            signals.extend(batch_signals)
            processed.extend(str(comment["id"]) for comment in batch)
        except Exception as exc:
            failed.append(
                FailedBatch(
                    batch_index=batch_index,
                    comment_ids=[str(comment["id"]) for comment in batch],
                    error=str(exc)[:240],
                )
            )
    return SignalAnalysisResult(signals, processed, failed, mode)


def retry_failed_batches(
    comments: list[dict],
    failed_batches: list[dict],
    client: OpenAICompatibleClient | None = None,
    batch_size: int = 40,
    topic_hint: str = "",
) -> SignalAnalysisResult:
    indexes = {int(batch["batch_index"]) for batch in failed_batches}
    return analyze_comments(
        comments,
        client=client,
        batch_size=batch_size,
        batch_indexes=indexes,
        topic_hint=topic_hint,
    )


def _analyze_model_batch(
    batch: list[dict], client: OpenAICompatibleClient, schema_retries: int = 2
) -> list[Signal]:
    payload = [
        {"comment_id": comment["id"], "text": comment["content"]}
        for comment in batch
    ]
    user_prompt = "请分析以下评论：\n" + json.dumps(payload, ensure_ascii=False)
    last_error: Exception | None = None
    for _ in range(schema_retries + 1):
        try:
            response = client.complete_json(SYSTEM_PROMPT, user_prompt)
            return validate_signal_response(response, batch)
        except (ValueError, LLMResponseError) as exc:
            last_error = exc
    raise LLMResponseError(f"批次结构校验失败：{last_error}")


def validate_signal_response(response: dict, comments: list[dict]) -> list[Signal]:
    _reject_forbidden_statistics(response)
    results = response.get("results")
    if not isinstance(results, list):
        raise ValueError("响应缺少 results 数组。")

    comment_by_id = {str(comment["id"]): comment for comment in comments}
    returned_ids = [str(item.get("comment_id", "")) for item in results if isinstance(item, dict)]
    if len(returned_ids) != len(set(returned_ids)):
        raise ValueError("响应包含重复评论 ID。")
    if set(returned_ids) != set(comment_by_id):
        missing = sorted(set(comment_by_id) - set(returned_ids))
        unknown = sorted(set(returned_ids) - set(comment_by_id))
        raise ValueError(f"评论 ID 不匹配，缺失={missing}，未知={unknown}。")

    signals: list[Signal] = []
    for result in results:
        comment_id = str(result["comment_id"])
        raw_signals = result.get("signals", [])
        if not isinstance(raw_signals, list):
            raise ValueError(f"{comment_id} 的 signals 必须是数组。")
        original_text = str(comment_by_id[comment_id]["content"])
        for signal_index, raw in enumerate(raw_signals, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"{comment_id} 包含非法信号。")
            signal_type = str(raw.get("type", ""))
            if signal_type not in SIGNAL_TYPES:
                raise ValueError(f"非法信号类型：{signal_type}")
            try:
                emotion = int(raw.get("emotion_level", 1))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{comment_id} 的情绪评分不是整数。") from exc
            emotion = max(1, min(5, emotion))
            evidence = str(raw.get("evidence_span", "")).strip()
            if not evidence or evidence not in original_text:
                evidence = original_text
            signals.append(
                Signal(
                    id=f"SIG-{comment_id.removeprefix('C-')}-{signal_index:02d}",
                    comment_id=comment_id,
                    type=signal_type,
                    topic=str(raw.get("topic", "")).strip() or "未命名主题",
                    need=str(raw.get("need", "")).strip(),
                    concern=str(raw.get("concern", "")).strip(),
                    audience=str(raw.get("audience", "")).strip(),
                    scene=str(raw.get("scene", "")).strip(),
                    emotion_level=emotion,
                    evidence_span=evidence,
                )
            )
    return signals


def _reject_forbidden_statistics(value: object) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_OUTPUT_KEYS.intersection(value)
        if forbidden:
            raise ValueError(f"模型输出了禁止的统计字段：{sorted(forbidden)}")
        for nested in value.values():
            _reject_forbidden_statistics(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_forbidden_statistics(nested)


def _analyze_local_batch(batch: list[dict], topic_hint: str = "") -> list[Signal]:
    signals: list[Signal] = []
    for comment in batch:
        text = str(comment["content"])
        signal_specs = _local_signal_specs(text, topic_hint)
        for index, spec in enumerate(signal_specs, start=1):
            signals.append(
                Signal(
                    id=f"SIG-{str(comment['id']).removeprefix('C-')}-{index:02d}",
                    comment_id=str(comment["id"]),
                    evidence_span=text,
                    emotion_level=_emotion_level(text),
                    **spec,
                )
            )
    return signals


def _local_signal_specs(text: str, topic_hint: str = "") -> list[dict]:
    topic = _topic_for_text(text, topic_hint)
    audience = _audience_for_text(text)
    scene = _scene_for_text(text)
    specs: list[dict] = []
    if any(marker in text for marker in ("但", "又怕", "反而", "不代表", "自我安慰", "越喝越")):
        specs.append(
            _spec("需求矛盾", topic, f"希望获得{topic}相关收益", "担心选择方案带来新的代价", audience, scene)
        )
    if any(marker in text for marker in ("吗", "？", "?", "为什么", "怎么", "多少", "区别", "有没有")):
        specs.append(_spec("高频疑问", topic, "需要清晰、可核验的解释", "现有内容没有直接回答", audience, scene))
    if any(marker in text for marker in ("有人说", "朋友总说", "到底", "一定", "还是", "所谓", "心理作用")):
        specs.append(_spec("观点分歧", topic, "希望验证不同说法", "评论区观点相互冲突", audience, scene))
    if any(marker in text for marker in ("对比", "测评", "哪个", "哪款", "不同品牌", "普通版", "进口", "红黑榜", "怎么选")):
        specs.append(_spec("对比需求", topic, "需要可执行的选择依据", "缺少统一比较标准", audience, scene))
    if scene:
        specs.append(_spec("隐藏场景", topic, "需要场景化选择建议", "通用建议无法覆盖具体使用条件", audience, scene))
    return _dedupe_specs(specs)


def _spec(signal_type: str, topic: str, need: str, concern: str, audience: str, scene: str) -> dict:
    return {
        "type": signal_type,
        "topic": topic,
        "need": need,
        "concern": concern,
        "audience": audience,
        "scene": scene,
    }


def _dedupe_specs(specs: Iterable[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    output: list[dict] = []
    for spec in specs:
        key = (spec["type"], spec["topic"])
        if key not in seen:
            seen.add(key)
            output.append(spec)
    return output


def _topic_for_text(text: str, topic_hint: str = "") -> str:
    topic_rules = (
        (("代糖", "赤藓糖醇", "阿斯巴甜", "甜味"), "代糖安全与甜味"),
        (("血糖", "糖尿病", "控糖", "糖分"), "控糖与血糖"),
        (("减脂", "减肥", "热量", "胖", "健身"), "减脂与热量"),
        (("配料", "营养成分", "碳水", "无添加糖", "零卡"), "配料与营养标签"),
        (("咖啡因", "睡不着", "失眠", "犯困"), "咖啡因与睡眠"),
        (("肠道", "肚子", "胃", "乳糖"), "肠胃耐受"),
        (("牙", "酸度"), "口腔健康"),
        (("孕", "孩子", "儿童", "痛风"), "特殊人群适用性"),
        (("品牌", "哪款", "测评", "红黑榜", "国产", "进口"), "产品横向对比"),
    )
    for keywords, topic in topic_rules:
        if any(keyword in text for keyword in keywords):
            return topic
    return topic_hint.strip() or "评论中的内容需求"


def _audience_for_text(text: str) -> str:
    audience_rules = (
        (("控糖", "血糖", "糖尿病"), "控糖人群"),
        (("减脂", "减肥", "健身", "跑步"), "减脂健身人群"),
        (("孕",), "孕期人群"),
        (("孩子", "儿童"), "有儿童的家庭"),
        (("痛风",), "特殊健康需求人群"),
        (("肠", "胃", "乳糖"), "肠胃敏感人群"),
    )
    for keywords, audience in audience_rules:
        if any(keyword in text for keyword in keywords):
            return audience
    return "关注该主题的用户"


def _scene_for_text(text: str) -> str:
    scene_rules = (
        (("办公室", "下午", "犯困"), "办公室下午"),
        (("晚上", "加班"), "晚间或加班"),
        (("火锅", "聚餐"), "聚餐佐餐"),
        (("跑步", "健身后"), "运动后"),
        (("早上", "空腹"), "早晨空腹"),
        (("餐前", "餐后"), "用餐前后"),
        (("便利店",), "便利店即时购买"),
        (("冰镇", "常温"), "不同饮用温度"),
        (("戒糖",), "戒糖过渡期"),
    )
    for keywords, scene in scene_rules:
        if any(keyword in text for keyword in keywords):
            return scene
    return ""


def _emotion_level(text: str) -> int:
    score = 2
    if any(marker in text for marker in ("担心", "怕", "不舒服", "刺激", "伤", "安全吗")):
        score += 1
    if any(marker in text for marker in ("到底", "真的", "总说", "越喝越", "别只说")):
        score += 1
    return min(5, score)
