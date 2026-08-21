from __future__ import annotations

import json

from scripts.build_demo_analysis import ROOT
from services.brief_service import generate_briefs
from services.clean_service import clean_comments
from services.demo_service import DEMO_BRIEFS_FILE, load_demo_analysis
from services.import_service import inspect_file, materialize_records
from services.view_service import filter_opportunities


def main() -> None:
    analysis = load_demo_analysis()
    raw = materialize_records(inspect_file(ROOT / "data" / "demo" / "sugar_free_comments.csv"))
    comments, quality = clean_comments(raw, "T-DEMO")
    state = {
        **analysis,
        "task": {"id": "T-DEMO", "topic": "无糖饮料", "industry": "食品饮料", "status": "completed"},
        "comments": [comment.to_dict() for comment in comments],
        "quality": quality.to_dict(),
    }
    formal, _ = filter_opportunities(state["opportunities"])
    payload = {
        "version": 1,
        "opportunities": {item["id"]: generate_briefs(item["id"], state) for item in formal},
    }
    DEMO_BRIEFS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {DEMO_BRIEFS_FILE}: {len(formal)} opportunities, {len(formal) * 3} briefs")


if __name__ == "__main__":
    main()
