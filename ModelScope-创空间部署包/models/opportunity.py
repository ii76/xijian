from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Opportunity:
    id: str
    task_id: str
    name: str
    insight: str
    signal_types: list[str]
    comment_ids: list[str]
    audiences: list[str]
    scenes: list[str]
    tension_level: int
    emotion_level: int
    audience_clarity: int
    content_convertibility: int
    signal_ids: list[str] = field(default_factory=list)
    cluster_cohesion: float = 0.0
    label_consistency: float = 0.0
    weak_signal: bool = False
    comment_count: int = 0
    coverage_rate: float = 0.0
    gap_score: int = 0
    priority: str = "补充观察"
    confidence: str = "低"
    score_detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
