from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from collections import OrderedDict
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any

from models.comment import Comment


INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
TAG_SPACE_RE = re.compile(r"\s+")
REPEATED_PUNCTUATION_RE = re.compile(r"([!?！？。,.，；;：:~～])\1{2,}")
PURE_NUMBER_RE = re.compile(r"^[\s+\-.,，]*\d+(?:[.,]\d+)?[\s%％]*$")
HAS_MEANINGFUL_CHAR_RE = re.compile(r"[A-Za-z\u3400-\u9fff]")
NOISE_TRIM_RE = re.compile(r"[\s!?！？。,.，；;：:~～哈呵嘿嘻]+")
LOW_INFORMATION = {
    "路过",
    "沙发",
    "板凳",
    "打卡",
    "围观",
    "来了",
    "666",
    "哈哈",
    "哈哈哈",
    "呵呵",
    "嘿嘿",
    "嘻嘻",
    "赞",
    "支持",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


@dataclass(slots=True)
class QualitySummary:
    raw_count: int
    unique_count: int
    valid_count: int
    invalid_count: int
    duplicate_count: int
    effective_rate: float
    sample_warning: bool
    quality_warning: bool
    all_duplicate: bool
    analysis_ready: bool

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    extractor = _TextExtractor()
    try:
        extractor.feed(text)
        text = extractor.text()
    except Exception:
        text = re.sub(r"<[^>]*>", " ", text)
    text = html.unescape(text)
    text = INVISIBLE_RE.sub("", text)
    text = TAG_SPACE_RE.sub(" ", text).strip()
    text = REPEATED_PUNCTUATION_RE.sub(lambda match: match.group(1) * 2, text)
    return text


def classify_validity(text: str) -> tuple[bool, str | None]:
    if not text:
        return False, "空内容"
    compact = re.sub(r"\s+", "", text).casefold()
    if PURE_NUMBER_RE.fullmatch(compact):
        return False, "纯数字"
    if compact in LOW_INFORMATION:
        return False, "低信息文本"
    if not HAS_MEANINGFUL_CHAR_RE.search(compact):
        return False, "纯表情或符号"
    if not NOISE_TRIM_RE.sub("", compact):
        return False, "低信息文本"
    return True, None


def _safe_like_count(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def clean_comments(raw_records: list[dict], task_id: str) -> tuple[list[Comment], QualitySummary]:
    grouped: OrderedDict[str, dict] = OrderedDict()
    for raw in raw_records:
        text = normalize_text(raw.get("text"))
        key = text
        if key in grouped:
            grouped[key]["duplicate_count"] += 1
            continue
        grouped[key] = {
            "text": text,
            "source_platform": str(raw.get("source_platform") or "unknown"),
            "like_count": _safe_like_count(raw.get("like_count")),
            "published_at": raw.get("published_at"),
            "duplicate_count": 1,
        }

    comments: list[Comment] = []
    for index, item in enumerate(grouped.values(), start=1):
        valid, reason = classify_validity(item["text"])
        digest = hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
        comments.append(
            Comment(
                id=f"C-{index:04d}",
                task_id=task_id,
                content=item["text"],
                source_platform=item["source_platform"],
                like_count=item["like_count"],
                published_at=item["published_at"],
                valid=valid,
                duplicate_count=item["duplicate_count"],
                raw_hash=digest,
                invalid_reason=reason,
            )
        )

    raw_count = len(raw_records)
    unique_count = len(comments)
    valid_count = sum(comment.valid for comment in comments)
    invalid_count = unique_count - valid_count
    duplicate_count = raw_count - unique_count
    effective_rate = valid_count / raw_count if raw_count else 0.0
    all_duplicate = raw_count > 1 and unique_count == 1
    quality_warning = effective_rate < 0.5
    summary = QualitySummary(
        raw_count=raw_count,
        unique_count=unique_count,
        valid_count=valid_count,
        invalid_count=invalid_count,
        duplicate_count=duplicate_count,
        effective_rate=effective_rate,
        sample_warning=valid_count < 20,
        quality_warning=quality_warning,
        all_duplicate=all_duplicate,
        analysis_ready=valid_count > 0 and not all_duplicate,
    )
    return comments, summary
