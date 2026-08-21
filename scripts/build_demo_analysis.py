from __future__ import annotations

import json
from pathlib import Path

from services.clean_service import clean_comments
from services.cluster_service import cluster_signals
from services.demo_service import DEMO_ANALYSIS_FILE
from services.import_service import inspect_file, materialize_records
from services.score_service import score_opportunities
from services.signal_service import analyze_comments


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    raw = materialize_records(inspect_file(ROOT / "data" / "demo" / "sugar_free_comments.csv"))
    comments, _ = clean_comments(raw, "T-DEMO")
    comment_dicts = [comment.to_dict() for comment in comments]
    analysis = analyze_comments(comment_dicts)
    opportunities = score_opportunities(
        cluster_signals(analysis.signals, "T-DEMO"), comment_dicts
    )
    payload = {
        "version": 1,
        "mode": "precomputed_demo",
        "signals": [signal.to_dict() for signal in analysis.signals],
        "opportunities": [opportunity.to_dict() for opportunity in opportunities],
        "processed_comment_ids": analysis.processed_comment_ids,
        "failed_batches": [],
    }
    DEMO_ANALYSIS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {DEMO_ANALYSIS_FILE}: "
        f"{len(payload['signals'])} signals, {len(payload['opportunities'])} opportunities"
    )


if __name__ == "__main__":
    main()

