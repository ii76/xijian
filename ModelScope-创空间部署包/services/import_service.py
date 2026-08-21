from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


MAX_FILE_BYTES = 10 * 1024 * 1024
COMMENT_COLUMN_ALIASES = (
    "comment",
    "comments",
    "content",
    "text",
    "comment_text",
    "评论",
    "评论内容",
    "内容",
    "正文",
)
PLATFORM_COLUMN_ALIASES = ("platform", "source_platform", "source", "平台", "来源平台")
LIKE_COLUMN_ALIASES = ("like_count", "likes", "like", "点赞数", "点赞")
DATE_COLUMN_ALIASES = ("published_at", "date", "time", "发布时间", "日期")


class ImportDataError(ValueError):
    """Raised when an uploaded dataset cannot be safely parsed."""


def _normalized_name(value: Any) -> str:
    return str(value).strip().casefold().replace(" ", "_")


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    lookup = {_normalized_name(column): column for column in columns}
    for alias in aliases:
        match = lookup.get(_normalized_name(alias))
        if match is not None:
            return match
    return None


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def _dataframe_payload(frame: pd.DataFrame, source_name: str, source_type: str) -> dict:
    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    columns = list(frame.columns)
    records = [
        {column: _json_value(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    return {
        "source_name": source_name,
        "source_type": source_type,
        "columns": columns,
        "rows": records,
        "detected_comment_column": _find_column(columns, COMMENT_COLUMN_ALIASES),
        "platform_column": _find_column(columns, PLATFORM_COLUMN_ALIASES),
        "like_column": _find_column(columns, LIKE_COLUMN_ALIASES),
        "date_column": _find_column(columns, DATE_COLUMN_ALIASES),
    }


def inspect_file(file_path: str | Path) -> dict:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise ImportDataError("上传文件不存在，请重新选择。")
    if path.stat().st_size == 0:
        raise ImportDataError("文件为空，无法导入。")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ImportDataError("文件超过 10 MB，请拆分后重新上传。")

    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            frame = _read_csv(path)
        elif suffix == ".xlsx":
            frame = pd.read_excel(path, engine="openpyxl", dtype=object)
        else:
            raise ImportDataError("仅支持 CSV 和 XLSX 文件。")
    except ImportDataError:
        raise
    except Exception as exc:
        raise ImportDataError(f"文件解析失败：{exc}") from exc

    if frame.empty or not len(frame.columns):
        raise ImportDataError("文件没有可读取的数据行。")
    return _dataframe_payload(frame, path.name, "file")


def _read_csv(path: Path) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return pd.read_csv(path, encoding=encoding, dtype=object)
        except UnicodeDecodeError as exc:
            errors.append(str(exc))
        except pd.errors.EmptyDataError as exc:
            raise ImportDataError("CSV 文件为空。") from exc
        except pd.errors.ParserError as exc:
            raise ImportDataError("CSV 结构异常，请检查分隔符和引号。") from exc
    raise ImportDataError("无法识别文件编码，请转换为 UTF-8 后重试。")


def parse_pasted_text(text: str) -> dict:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        raise ImportDataError("请粘贴至少一条非空评论。")
    frame = pd.DataFrame({"comment": lines})
    return _dataframe_payload(frame, "粘贴文本", "pasted_text")


def materialize_records(payload: dict, comment_column: str | None = None) -> list[dict]:
    if not payload or not payload.get("rows"):
        raise ImportDataError("尚未导入评论。")
    selected = comment_column or payload.get("detected_comment_column")
    if not selected or selected not in payload.get("columns", []):
        raise ImportDataError("请选择包含评论正文的列。")

    platform_column = payload.get("platform_column")
    like_column = payload.get("like_column")
    date_column = payload.get("date_column")
    records: list[dict] = []
    for row in payload["rows"]:
        records.append(
            {
                "text": row.get(selected),
                "source_platform": row.get(platform_column) if platform_column else "unknown",
                "like_count": row.get(like_column) if like_column else 0,
                "published_at": row.get(date_column) if date_column else None,
            }
        )
    return records


def import_summary(payload: dict, comment_column: str | None = None) -> dict:
    records = materialize_records(payload, comment_column)
    abnormal = sum(1 for item in records if item["text"] is None or not str(item["text"]).strip())
    return {
        "source_name": payload["source_name"],
        "row_count": len(records),
        "abnormal_count": abnormal,
        "comment_column": comment_column or payload.get("detected_comment_column"),
        "has_platform": bool(payload.get("platform_column")),
        "has_likes": bool(payload.get("like_column")),
    }


def preview_rows(payload: dict, comment_column: str | None = None, limit: int = 10) -> list[list]:
    records = materialize_records(payload, comment_column)
    return [
        [
            "" if item["text"] is None else str(item["text"]),
            item["source_platform"] or "unknown",
            _safe_like_count(item["like_count"]),
        ]
        for item in records[:limit]
    ]


def _safe_like_count(value: Any) -> int:
    try:
        if value is None or pd.isna(value):
            return 0
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0
