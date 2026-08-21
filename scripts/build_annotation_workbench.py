from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import app


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "materials" / "annotation_workbench_100.csv"
FIELDS = (
    "序号", "评论ID", "评论内容", "是否有效", "信号类型", "讨论主题", "用户需求",
    "用户顾虑", "目标人群", "使用场景", "人工复核状态", "复核人", "备注",
)


def top(values) -> str:
    counts = Counter(value for value in values if value)
    return counts.most_common(1)[0][0] if counts else ""


def main() -> None:
    payload = app.load_demo_payload()
    clean = app.handle_clean("无糖饮料", "食品饮料", ["科普", "测评"], [], "", "comment", payload)
    state = app.handle_demo_precomputed(clean[5], clean[4])[5]
    signals_by_comment: dict[str, list[dict]] = {}
    for signal in state["signals"]:
        signals_by_comment.setdefault(signal["comment_id"], []).append(signal)
    rows = []
    for index, comment in enumerate(state["comments"], start=1):
        signals = signals_by_comment.get(comment["id"], [])
        rows.append(
            {
                "序号": index,
                "评论ID": comment["id"],
                "评论内容": comment["content"],
                "是否有效": "是" if comment.get("valid", True) else "否",
                "信号类型": "/".join(sorted({item["type"] for item in signals})),
                "讨论主题": top(item.get("topic", "") for item in signals),
                "用户需求": top(item.get("need", "") for item in signals),
                "用户顾虑": top(item.get("concern", "") for item in signals),
                "目标人群": top(item.get("audience", "") for item in signals),
                "使用场景": top(item.get("scene", "") for item in signals),
                "人工复核状态": "待人工复核",
                "复核人": "",
                "备注": "系统预标注，不计入已完成人工标注",
            }
        )
    while len(rows) < 100:
        rows.append(
            {
                "序号": len(rows) + 1,
                "评论ID": "",
                "评论内容": "",
                "是否有效": "",
                "信号类型": "",
                "讨论主题": "",
                "用户需求": "",
                "用户顾虑": "",
                "目标人群": "",
                "使用场景": "",
                "人工复核状态": "待补充真实评论",
                "复核人": "",
                "备注": "补充匿名真实评论后再进行人工标注",
            }
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUTPUT}: {len(rows)} rows, {len(state['comments'])} pre-labeled")


if __name__ == "__main__":
    main()
