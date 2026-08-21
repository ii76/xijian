from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import app
from services.brief_service import generate_briefs
from services.release_service import validate_release_state
from services.view_service import filter_opportunities


ROOT = Path(__file__).resolve().parents[1]
REPORT_FILE = ROOT / "materials" / "release_metrics.json"


def run_once() -> dict:
    payload = app.load_demo_payload()
    clean = app.handle_clean("无糖饮料", "食品饮料", ["科普", "测评"], [], "", "comment", payload)
    state = app.handle_demo_precomputed(clean[5], clean[4])[5]
    formal, _ = filter_opportunities(state["opportunities"])
    briefs = generate_briefs(formal[0]["id"], state)
    if len(briefs) != 3:
        raise RuntimeError("Brief generation did not return three plans")
    return validate_release_state(state)


def main() -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    runs = []
    started = perf_counter()
    for index in range(5):
        run_started = perf_counter()
        metrics = run_once()
        runs.append({"run": index + 1, "seconds": round(perf_counter() - run_started, 3), **metrics})
    passed = sum(
        item["traceability_rate"] == 1.0
        and item["numeric_program_rate"] == 1.0
        and item["brief_evidence_rate"] == 1.0
        for item in runs
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        "successful_runs": passed,
        "completion_rate": passed / len(runs),
        "total_seconds": round(perf_counter() - started, 3),
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
