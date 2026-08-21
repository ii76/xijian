from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class Task:
    topic: str
    industry: str
    content_goals: list[str]
    platforms: list[str] = field(default_factory=list)
    target_audience: str = ""
    status: str = "created"
    id: str = field(default_factory=lambda: f"T-{uuid4().hex[:10].upper()}")
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)

