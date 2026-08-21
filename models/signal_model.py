from dataclasses import asdict, dataclass, field
from uuid import uuid4


SIGNAL_TYPES = ("需求矛盾", "高频疑问", "观点分歧", "对比需求", "隐藏场景")


@dataclass(slots=True)
class Signal:
    comment_id: str
    type: str
    topic: str
    need: str = ""
    concern: str = ""
    audience: str = ""
    scene: str = ""
    emotion_level: int = 1
    evidence_span: str = ""
    id: str = field(default_factory=lambda: f"SIG-{uuid4().hex[:10].upper()}")

    def to_dict(self) -> dict:
        return asdict(self)
