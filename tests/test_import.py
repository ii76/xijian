from time import perf_counter
from pathlib import Path

import pandas as pd
import pytest

from services.import_service import (
    ImportDataError,
    import_summary,
    inspect_file,
    materialize_records,
    parse_pasted_text,
)


def test_csv_detects_chinese_comment_column(tmp_path: Path) -> None:
    path = tmp_path / "comments.csv"
    pd.DataFrame({"评论内容": ["代糖安全吗？", "想看横向测评"], "点赞数": [3, 5]}).to_csv(
        path, index=False, encoding="utf-8-sig"
    )
    payload = inspect_file(path)
    assert payload["source_type"] == "file"
    assert payload["detected_comment_column"] == "评论内容"
    assert payload["like_column"] == "点赞数"
    assert len(materialize_records(payload)) == 2


@pytest.mark.parametrize("column", ["comment", "content", "text", "评论内容"])
def test_required_comment_column_aliases_are_detected(tmp_path: Path, column: str) -> None:
    path = tmp_path / f"alias-{column}.csv"
    pd.DataFrame({column: ["想看无糖饮料测评"]}).to_csv(path, index=False)
    assert inspect_file(path)["detected_comment_column"] == column


def test_xlsx_import(tmp_path: Path) -> None:
    path = tmp_path / "comments.xlsx"
    pd.DataFrame({"text": ["晚上喝会睡不着吗？"], "platform": ["小红书"]}).to_excel(
        path, index=False
    )
    payload = inspect_file(path)
    records = materialize_records(payload)
    assert records[0]["source_platform"] == "小红书"


def test_manual_column_selection(tmp_path: Path) -> None:
    path = tmp_path / "unknown.csv"
    pd.DataFrame({"用户反馈": ["想知道代糖区别"]}).to_csv(path, index=False)
    payload = inspect_file(path)
    assert payload["detected_comment_column"] is None
    assert materialize_records(payload, "用户反馈")[0]["text"] == "想知道代糖区别"


def test_pasted_text_ignores_blank_lines() -> None:
    payload = parse_pasted_text("第一条\n\n 第二条 \n")
    assert payload["source_type"] == "pasted_text"
    assert [item["text"] for item in materialize_records(payload)] == ["第一条", "第二条"]


def test_gb18030_csv_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "gb18030.csv"
    pd.DataFrame({"评论内容": ["代糖安全吗？"]}).to_csv(
        path, index=False, encoding="gb18030"
    )
    assert materialize_records(inspect_file(path))[0]["text"] == "代糖安全吗？"


def test_preview_is_limited_to_ten_rows() -> None:
    from services.import_service import preview_rows

    payload = parse_pasted_text("\n".join(f"第{i}条评论" for i in range(20)))
    assert len(preview_rows(payload)) == 10


def test_500_comment_import_stays_within_stage_target(tmp_path: Path) -> None:
    path = tmp_path / "comments-500.csv"
    pd.DataFrame({"comment": [f"第{i}条有效评论" for i in range(500)]}).to_csv(
        path, index=False
    )
    started = perf_counter()
    payload = inspect_file(path)
    records = materialize_records(payload)
    assert perf_counter() - started < 5
    assert len(records) == 500


def test_import_summary_counts_empty_rows() -> None:
    payload = {
        "source_name": "test",
        "columns": ["comment"],
        "rows": [{"comment": "有效"}, {"comment": None}],
        "detected_comment_column": "comment",
        "platform_column": None,
        "like_column": None,
        "date_column": None,
    }
    assert import_summary(payload)["abnormal_count"] == 1


@pytest.mark.parametrize("name", ["bad.txt", "bad.json", "bad.xls"])
def test_rejects_unsupported_extensions(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_text("comment\nhello", encoding="utf-8")
    with pytest.raises(ImportDataError, match="仅支持"):
        inspect_file(path)


def test_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.touch()
    with pytest.raises(ImportDataError, match="为空"):
        inspect_file(path)
