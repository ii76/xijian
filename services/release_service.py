from __future__ import annotations

from services.brief_service import generate_briefs
from services.score_service import calculate_gap_score
from services.view_service import filter_opportunities


def validate_release_state(state: dict) -> dict:
    formal, weak = filter_opportunities(state.get("opportunities", []))
    comment_ids = {item["id"] for item in state.get("comments", [])}
    trace_checks = 0
    trace_passed = 0
    numeric_checks = 0
    numeric_passed = 0
    brief_checks = 0
    brief_passed = 0

    for opportunity in formal:
        trace_checks += 1
        if set(opportunity["comment_ids"]).issubset(comment_ids):
            trace_passed += 1
        score = opportunity["score_detail"]
        recomputed, _ = calculate_gap_score(
            opportunity["coverage_rate"],
            score["tension"]["level"],
            score["emotion"]["level"],
            score["audience"]["level"],
            score["convertibility"]["level"],
        )
        numeric_checks += 3
        numeric_passed += int(opportunity["comment_count"] == len(set(opportunity["comment_ids"])))
        numeric_passed += int(abs(opportunity["coverage_rate"] - opportunity["comment_count"] / state["quality"]["valid_count"]) < 1e-9)
        numeric_passed += int(opportunity["gap_score"] == recomputed)
        briefs = generate_briefs(opportunity["id"], state)
        for brief in briefs:
            brief_checks += 1
            if set(brief["evidence_comment_ids"]).issubset(set(opportunity["comment_ids"])):
                brief_passed += 1

    return {
        "formal_opportunities": len(formal),
        "weak_signals": len(weak),
        "traceability_rate": _rate(trace_passed, trace_checks),
        "numeric_program_rate": _rate(numeric_passed, numeric_checks),
        "brief_evidence_rate": _rate(brief_passed, brief_checks),
        "trace_checks": trace_checks,
        "numeric_checks": numeric_checks,
        "brief_checks": brief_checks,
    }


def _rate(passed: int, total: int) -> float:
    return passed / total if total else 0.0
