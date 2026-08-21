from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_ANALYSIS_FILE = ROOT / "data" / "demo" / "demo_analysis.json"
DEMO_BRIEFS_FILE = ROOT / "data" / "demo" / "demo_briefs.json"


def load_demo_analysis() -> dict:
    if not DEMO_ANALYSIS_FILE.exists():
        raise FileNotFoundError("示例预计算结果尚未生成。")
    payload = json.loads(DEMO_ANALYSIS_FILE.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError("示例预计算结果版本不兼容。")
    required = {"signals", "opportunities", "processed_comment_ids"}
    if not required.issubset(payload):
        raise ValueError("示例预计算结果字段不完整。")
    return payload


def load_demo_briefs() -> dict[str, list[dict]]:
    if not DEMO_BRIEFS_FILE.exists():
        return {}
    payload = json.loads(DEMO_BRIEFS_FILE.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("opportunities"), dict):
        raise ValueError("示例预生成 Brief 版本不兼容。")
    return payload["opportunities"]
