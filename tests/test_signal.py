import json

import pytest

from models.signal_model import SIGNAL_TYPES
from services.signal_service import analyze_comments, retry_failed_batches, validate_signal_response


def _comment(index: int, content: str = "代糖安全吗？") -> dict:
    return {"id": f"C-{index:04d}", "content": content, "valid": True}


def _valid_result(comments: list[dict]) -> dict:
    return {
        "results": [
            {
                "comment_id": comment["id"],
                "valid": True,
                "signals": [
                    {
                        "type": "高频疑问",
                        "topic": "代糖安全",
                        "need": "需要解释",
                        "concern": "担心风险",
                        "audience": "控糖人群",
                        "scene": "",
                        "emotion_level": 4,
                        "evidence_span": comment["content"],
                    }
                ],
            }
            for comment in comments
        ]
    }


def test_signal_response_binds_real_ids_and_clamps_emotion() -> None:
    comments = [_comment(1)]
    response = _valid_result(comments)
    response["results"][0]["signals"][0]["emotion_level"] = 9
    signals = validate_signal_response(response, comments)
    assert signals[0].comment_id == "C-0001"
    assert signals[0].emotion_level == 5


@pytest.mark.parametrize(
    "mutator",
    [
        lambda response: response["results"].append(response["results"][0].copy()),
        lambda response: response["results"].clear(),
        lambda response: response["results"][0].update(comment_id="C-9999"),
        lambda response: response["results"][0]["signals"][0].update(type="情感分析"),
        lambda response: response.update(gap_score=90),
    ],
)
def test_invalid_model_outputs_are_rejected(mutator) -> None:
    comments = [_comment(1)]
    response = _valid_result(comments)
    mutator(response)
    with pytest.raises(ValueError):
        validate_signal_response(response, comments)


def test_invalid_evidence_is_replaced_with_original_comment() -> None:
    comments = [_comment(1)]
    response = _valid_result(comments)
    response["results"][0]["signals"][0]["evidence_span"] = "不存在的证据"
    assert validate_signal_response(response, comments)[0].evidence_span == comments[0]["content"]


def test_100_comments_complete_in_batches(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    comments = [_comment(i, f"第{i}条评论，代糖安全吗？") for i in range(1, 101)]
    result = analyze_comments(comments, batch_size=40)
    assert len(result.processed_comment_ids) == 100
    assert len(set(result.processed_comment_ids)) == 100
    assert result.failed_batches == []


def test_one_comment_can_have_multiple_signal_types(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    comment = _comment(1, "健身后想喝无糖饮料，但又怕变胖，到底哪款更好？")
    result = analyze_comments([comment])
    types = {signal.type for signal in result.signals}
    assert {"需求矛盾", "高频疑问", "观点分歧", "对比需求", "隐藏场景"}.issubset(types)


class BatchClient:
    def __init__(self, fail_id: str | None = None) -> None:
        self.fail_id = fail_id

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        comments = json.loads(user_prompt.split("\n", 1)[1])
        if self.fail_id and any(item["comment_id"] == self.fail_id for item in comments):
            raise RuntimeError("planned batch failure")
        model_comments = [
            {"id": item["comment_id"], "content": item["text"]} for item in comments
        ]
        return _valid_result(model_comments)


def test_failed_batch_does_not_clear_successful_batches() -> None:
    comments = [_comment(i) for i in range(1, 71)]
    result = analyze_comments(comments, client=BatchClient("C-0031"), batch_size=30)
    assert len(result.processed_comment_ids) == 40
    assert len(result.failed_batches) == 1
    assert result.failed_batches[0].batch_index == 1

    retried = retry_failed_batches(
        comments, [result.failed_batches[0].to_dict()], client=BatchClient(), batch_size=30
    )
    assert len(retried.processed_comment_ids) == 30
    assert retried.failed_batches == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("无糖是好，但我担心代糖风险", "需求矛盾"),
        ("代糖到底安全吗？", "高频疑问"),
        ("有人说代糖好，也有人说不好", "观点分歧"),
        ("赤藓糖醇和阿斯巴甜哪个更好", "对比需求"),
        ("办公室下午犯困时喝什么", "隐藏场景"),
    ] * 4,
)
def test_twenty_manual_signal_examples(monkeypatch, text: str, expected: str) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = analyze_comments([_comment(1, text)])
    assert expected in {signal.type for signal in result.signals}
    assert all(signal.type in SIGNAL_TYPES for signal in result.signals)
