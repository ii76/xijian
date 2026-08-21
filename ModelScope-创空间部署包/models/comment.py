from dataclasses import asdict, dataclass


@dataclass(slots=True)
class Comment:
    id: str
    task_id: str
    content: str
    source_platform: str = "unknown"
    like_count: int = 0
    published_at: str | None = None
    valid: bool = True
    duplicate_count: int = 1
    raw_hash: str = ""
    invalid_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

