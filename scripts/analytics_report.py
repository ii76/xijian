from __future__ import annotations

import json
from pathlib import Path

from services.analytics_service import funnel_metrics


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "materials" / "analytics_summary.json"


def main() -> None:
    report = funnel_metrics()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
