from dataclasses import asdict, dataclass, field
from uuid import uuid4


@dataclass(slots=True)
class Brief:
    opportunity_id: str
    strategy: str
    title: str
    target_audience: str
    user_question: str
    content_goal: str
    angle: str
    format: str
    cover_copy: str
    hook: str
    structure: list[str]
    key_points: list[str]
    evidence_comment_ids: list[str]
    evidence_comments: list[dict]
    rationale: str
    risk_notice: str
    opportunity_name: str
    id: str = field(default_factory=lambda: f"BRF-{uuid4().hex[:10].upper()}")
    version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)
