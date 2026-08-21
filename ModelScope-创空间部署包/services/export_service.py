from __future__ import annotations

import re
import time
from pathlib import Path

from services.brief_service import brief_to_markdown
from services.view_service import filter_opportunities


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "exports"


def build_markdown_report(state: dict, briefs: list[dict]) -> str:
    task = state["task"]
    quality = state["quality"]
    formal, _ = filter_opportunities(state.get("opportunities", []))
    selected_id = briefs[0]["opportunity_id"] if briefs else ""
    selected = next((item for item in formal if item["id"] == selected_id), None)
    opportunities = "\n".join(
        f"- **{item['name']}**：隙值 {item['gap_score']}，{item['comment_count']} 条评论，"
        f"覆盖率 {item['coverage_rate']:.1%}。{item['insight']}"
        for item in formal
    ) or "- 暂无正式内容机会。"
    detail = (
        f"### {selected['name']}\n\n{selected['insight']}\n\n"
        f"- 隙值：{selected['gap_score']}\n- 优先级：{selected['priority']}\n"
        f"- 可信度：{selected['confidence']}\n- 关联评论：{selected['comment_count']} 条"
        if selected else "暂无重点机会。"
    )
    brief_text = "\n\n---\n\n".join(brief_to_markdown(item) for item in briefs)
    evidence = []
    seen = set()
    for brief in briefs:
        for item in brief["evidence_comments"]:
            if item["id"] not in seen:
                seen.add(item["id"])
                evidence.append(
                    f"> **{item['id']}** · {item.get('source_platform', 'unknown')} · {item.get('like_count', 0)} 赞\n> {item['content']}"
                )
    return f"""# 隙见内容机会报告：{task['topic']}

## 1. 数据概览

- 原始评论数：{quality['raw_count']}
- 去重后评论数：{quality['unique_count']}
- 有效评论数：{quality['valid_count']}

## 2. 主要内容机会

{opportunities}

## 3. 重点机会详情

{detail}

## 4. 内容 Brief

{brief_text}

## 5. 评论证据

{chr(10).join(evidence)}
"""


def export_markdown(state: dict, briefs: list[dict], directory: Path = EXPORT_DIR) -> Path:
    if not state or not briefs:
        raise ValueError("请先生成 Brief 再导出。")
    directory.mkdir(parents=True, exist_ok=True)
    cleanup_temp_files(directory)
    topic = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", state["task"]["topic"]).strip("-") or "report"
    path = directory / f"xijian-{topic}-{int(time.time())}.md"
    path.write_text(build_markdown_report(state, briefs), encoding="utf-8")
    return path


def cleanup_temp_files(directory: Path = EXPORT_DIR, max_age_seconds: int = 86400, keep: int = 20) -> int:
    if not directory.exists():
        return 0
    now = time.time()
    files = sorted(directory.glob("xijian-*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    removed = 0
    for index, path in enumerate(files):
        if index >= keep or now - path.stat().st_mtime > max_age_seconds:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
