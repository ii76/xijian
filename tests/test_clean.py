import pytest

from services.clean_service import classify_validity, clean_comments, normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  代糖安全吗？  ", "代糖安全吗?"),
        ("<b>无糖</b> 真的好吗", "无糖 真的好吗"),
        ("零糖\u200b饮料", "零糖饮料"),
        ("全角ＡＢＣ１２３", "全角ABC123"),
        ("安全吗？？？？", "安全吗??"),
    ],
)
def test_normalization_boundaries(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "代糖会升血糖吗",
        "不甜",
        "贵",
        "孕妇能喝吗？",
        "👍 但是真的好喝",
        "0糖为什么还有碳水",
        "无糖不等于健康",
        "想看横向测评",
        "晚上喝会失眠吗",
        "肠胃敏感人群怎么选",
        "赤藓糖醇和阿斯巴甜哪个好",
    ],
)
def test_meaningful_comments_are_valid(text: str) -> None:
    assert classify_validity(normalize_text(text))[0] is True


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "空内容"),
        ("1", "纯数字"),
        ("12345", "纯数字"),
        ("哈哈哈", "低信息文本"),
        ("路过", "低信息文本"),
        ("👍👍👍", "纯表情或符号"),
        ("……", "纯表情或符号"),
        ("666", "纯数字"),
        ("打卡", "低信息文本"),
    ],
)
def test_noise_comments_are_invalid(text: str, reason: str) -> None:
    assert classify_validity(normalize_text(text)) == (False, reason)


def test_exact_duplicates_are_counted_and_ids_are_stable() -> None:
    raw = [
        {"text": "代糖安全吗？", "source_platform": "demo"},
        {"text": " 代糖安全吗？ ", "source_platform": "demo"},
        {"text": "无糖茶和汽水哪个好？", "source_platform": "demo"},
    ]
    comments, summary = clean_comments(raw, "T-TEST")
    assert [item.id for item in comments] == ["C-0001", "C-0002"]
    assert comments[0].duplicate_count == 2
    assert summary.raw_count == 3
    assert summary.unique_count == 2
    assert summary.duplicate_count == 1


def test_similar_comments_are_not_removed() -> None:
    raw = [{"text": "代糖安全吗"}, {"text": "代糖长期安全吗"}]
    comments, _ = clean_comments(raw, "T-TEST")
    assert len(comments) == 2


def test_all_duplicate_comments_block_analysis() -> None:
    comments, summary = clean_comments([{"text": "代糖安全吗"}] * 3, "T-TEST")
    assert len(comments) == 1
    assert summary.all_duplicate is True
    assert summary.analysis_ready is False


def test_no_valid_comments_block_analysis() -> None:
    _, summary = clean_comments([{"text": "哈哈哈"}, {"text": "👍👍"}, {"text": "1"}], "T-TEST")
    assert summary.valid_count == 0
    assert summary.analysis_ready is False


def test_emoji_heavy_dataset_reports_low_quality() -> None:
    raw = [{"text": "👍👍"}] * 8 + [{"text": "代糖安全吗"}, {"text": "想看测评"}]
    _, summary = clean_comments(raw, "T-TEST")
    assert summary.effective_rate == pytest.approx(0.2)
    assert summary.quality_warning is True


def test_comment_ids_are_stable_across_repeated_runs() -> None:
    raw = [{"text": "代糖安全吗"}, {"text": "想看品牌横向测评"}]
    first, _ = clean_comments(raw, "T-TEST")
    second, _ = clean_comments(raw, "T-TEST")
    assert [(item.id, item.raw_hash) for item in first] == [
        (item.id, item.raw_hash) for item in second
    ]


def test_quality_numbers_can_be_recalculated() -> None:
    raw = [{"text": "代糖安全吗"}, {"text": "代糖安全吗"}, {"text": "哈哈哈"}, {"text": "1"}]
    comments, summary = clean_comments(raw, "T-TEST")
    assert summary.raw_count == 4
    assert summary.unique_count == 3
    assert summary.valid_count == 1
    assert summary.invalid_count == 2
    assert summary.effective_rate == pytest.approx(0.25)
    assert sum(item.duplicate_count for item in comments) == summary.raw_count


def test_raw_hash_does_not_expose_comment_text() -> None:
    comments, _ = clean_comments([{"text": "一条需要匿名处理的评论"}], "T-TEST")
    assert len(comments[0].raw_hash) == 64
    assert "一条" not in comments[0].raw_hash
