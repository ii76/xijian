from __future__ import annotations

import html
from collections import Counter

from models.brief import Brief
from services.view_service import build_detail


FORBIDDEN_CLAIMS = ("必爆", "百分百", "绝对安全", "保证有效", "医学证明")
HEALTH_WORDS = ("健康", "安全", "血糖", "减脂", "孕", "咖啡因", "热量", "身体")


def generate_briefs(opportunity_id: str, state: dict, version: int = 1) -> list[dict]:
    detail = build_detail(opportunity_id, state)
    opportunity = detail["opportunity"]
    evidence = _select_evidence(detail["evidence"])
    if len(evidence) < 3:
        raise ValueError("当前机会不足 3 条真实评论证据，不能生成 Brief。")

    strategies = _compatible_strategies(detail)
    briefs = [
        _build_brief(strategy, detail, evidence, version + index)
        for index, strategy in enumerate(strategies)
    ]
    validate_briefs(briefs, opportunity_id)
    return [brief.to_dict() for brief in briefs]


def regenerate_brief(
    opportunity_id: str, state: dict, current_briefs: list[dict], index: int
) -> list[dict]:
    if index < 0 or index >= len(current_briefs):
        raise ValueError("要重新生成的方案不存在。")
    refreshed = generate_briefs(
        opportunity_id,
        state,
        version=max(int(item.get("version", 1)) for item in current_briefs) + 1,
    )
    output = [dict(item) for item in current_briefs]
    output[index] = refreshed[index]
    validate_briefs(output, opportunity_id)
    return output


def brief_to_markdown(brief: dict) -> str:
    structure = "\n".join(
        f"{index}. {item}" for index, item in enumerate(brief["structure"], start=1)
    )
    points = "\n".join(f"- {item}" for item in brief["key_points"])
    evidence = "\n".join(
        f"> {item['id']} · {item.get('source_platform', 'unknown')} · "
        f"{item.get('like_count', 0)} 赞\n> {item['content']}"
        for item in brief["evidence_comments"]
    )
    return f"""### {brief['title']}

- **内容策略：** {brief['strategy']}
- **目标人群：** {brief['target_audience']}
- **核心用户问题：** {brief['user_question']}
- **内容目标：** {brief['content_goal']}
- **内容角度：** {brief['angle']}
- **推荐形式：** {brief['format']}
- **封面文案：** {brief['cover_copy']}
- **前三秒钩子：** {brief['hook']}
- **对应机会：** {brief['opportunity_name']}（`{brief['opportunity_id']}`）
- **证据评论数量：** {len(brief['evidence_comment_ids'])}

**内容结构**

{structure}

**核心观点**

{points}

**为什么值得做**

{brief['rationale']}

**评论证据**

{evidence}

**风险提示**

{brief['risk_notice']}
"""


def render_brief_html(brief: dict, index: int) -> str:
    structure = "".join(
        f"<li>{html.escape(item)}</li>" for item in brief["structure"]
    )
    points = "".join(f"<li>{html.escape(item)}</li>" for item in brief["key_points"])
    evidence = "".join(
        f"<blockquote><b>{html.escape(item['id'])}</b> · "
        f"{html.escape(item.get('source_platform', 'unknown'))} · {item.get('like_count', 0)} 赞<br>"
        f"{html.escape(item['content'])}</blockquote>"
        for item in brief["evidence_comments"]
    )
    return f"""
<article class="brief-card" id="brief-card-{index}">
  <header><span>{html.escape(brief['strategy'])}</span><small>方案 {index + 1}</small>
    <h3>{html.escape(brief['title'])}</h3></header>
  <div class="brief-meta">
    <p><b>目标人群</b>{html.escape(brief['target_audience'])}</p>
    <p><b>核心问题</b>{html.escape(brief['user_question'])}</p>
    <p><b>内容目标</b>{html.escape(brief['content_goal'])}</p>
    <p><b>推荐形式</b>{html.escape(brief['format'])}</p>
  </div>
  <section><b>内容角度</b><p>{html.escape(brief['angle'])}</p></section>
  <div class="brief-hook"><b>封面</b><p>{html.escape(brief['cover_copy'])}</p>
    <b>前三秒钩子</b><p>{html.escape(brief['hook'])}</p></div>
  <section><b>内容结构</b><ol>{structure}</ol></section>
  <section><b>核心观点</b><ul>{points}</ul></section>
  <section><b>为什么值得做</b><p>{html.escape(brief['rationale'])}</p></section>
  <section class="brief-evidence"><b>评论证据 · {len(brief['evidence_comment_ids'])} 条</b>{evidence}</section>
  <section class="risk-notice"><b>风险提示</b><p>{html.escape(brief['risk_notice'])}</p></section>
</article>
"""


def validate_briefs(briefs: list[Brief] | list[dict], opportunity_id: str) -> None:
    if len(briefs) != 3:
        raise ValueError("每个机会必须生成 3 份 Brief。")
    strategies = []
    for raw in briefs:
        item = raw.to_dict() if isinstance(raw, Brief) else raw
        required = (
            "strategy", "title", "target_audience", "user_question", "content_goal",
            "angle", "format", "cover_copy", "hook", "structure", "key_points",
            "evidence_comment_ids", "evidence_comments", "rationale", "risk_notice",
        )
        if any(not item.get(field) for field in required):
            raise ValueError("Brief 字段不完整。")
        if item["opportunity_id"] != opportunity_id:
            raise ValueError("Brief 与当前内容机会不一致。")
        if len(item["evidence_comment_ids"]) < 3:
            raise ValueError("Brief 至少需要 3 条评论证据。")
        if len(item["structure"]) < 3 or len(item["structure"]) > 5:
            raise ValueError("内容结构必须包含 3-5 段。")
        serialized = str(item)
        if any(claim in serialized for claim in FORBIDDEN_CLAIMS):
            raise ValueError("Brief 包含无法验证的绝对化表达。")
        strategies.append(item["strategy"])
    if len(set(strategies)) != 3:
        raise ValueError("三份 Brief 的内容策略必须不同。")


def _compatible_strategies(detail: dict) -> list[str]:
    types = set(detail["opportunity"].get("signal_types", []))
    first = "疑虑破除型" if detail.get("concerns") else "知识科普型"
    second = "观点验证型" if "观点分歧" in types else "横向测评型"
    third = "场景解决型" if detail["opportunity"].get("scenes") else "清单推荐型"
    return [first, second, third]


def _select_evidence(evidence: list[dict]) -> list[dict]:
    ranked = sorted(
        evidence,
        key=lambda item: (-len(item.get("signal_types", [])), -item.get("like_count", 0), item["comment_id"]),
    )
    return ranked[: min(5, len(ranked))]


def _build_brief(strategy: str, detail: dict, evidence: list[dict], version: int) -> Brief:
    opportunity = detail["opportunity"]
    audience = "、".join(opportunity.get("audiences", [])[:3]) or "关注该话题的消费者"
    question = evidence[(version - 1) % len(evidence)]["content"].rstrip("。！？?!")
    topic = opportunity["name"].replace("看懂", "")
    variants = {
        "疑虑破除型": {
            "title": f"{topic}到底该担心什么？把判断边界一次说清",
            "goal": "科普",
            "angle": "从真实顾虑出发，区分已知信息、适用边界和待核验问题",
            "format": "短视频或图文问答",
            "cover": f"{topic}，先看这 3 个判断边界",
            "hook": f"大家真正担心的不是一个结论，而是：{question}？",
            "structure": [
                "用一条代表性评论还原用户顾虑，不先下结论",
                "拆开概念、使用场景与个体差异三个判断层次",
                "给出可核对的信息来源和配料/标签检查方法",
                "总结适用边界，并邀请用户补充自己的具体场景",
            ],
            "points": ["先定义问题再讨论风险", "把结论限定在可核验信息内", "个体健康决策应咨询专业人士"],
        },
        "观点验证型": {
            "title": f"关于{topic}的两种说法，证据分别支持到哪一步？",
            "goal": "观点辨析",
            "angle": "并列呈现不同观点，用统一标准核对证据强弱",
            "format": "双观点短视频或长图",
            "cover": "两种说法，别急着站队",
            "hook": f"同一个问题为什么答案完全不同：{question}？",
            "structure": [
                "展示评论中的两类典型立场",
                "统一比较定义、使用条件和证据来源",
                "指出双方各自成立的边界与未知部分",
                "给出观众可以自行核验的三项检查清单",
            ],
            "points": ["不同观点先对齐讨论前提", "证据强度不等于表达强度", "保留尚无定论的部分"],
        },
        "横向测评型": {
            "title": f"{topic}怎么选？用 4 个维度做一次横向比较",
            "goal": "测评",
            "angle": "围绕评论中的比较需求建立透明评价维度，不预设品牌胜负",
            "format": "横向测评图文或视频",
            "cover": f"{topic}横向比较：看懂 4 个维度",
            "hook": f"别只看一个标签，用户问得最多的是：{question}？",
            "structure": [
                "说明测评问题和样本选择原则",
                "比较标签信息、适用场景、口感偏好和使用边界",
                "逐项展示信息来源，缺失数据明确标注",
                "按不同人群给出选择检查表，而非唯一答案",
            ],
            "points": ["测评标准公开且一致", "不虚构品牌或检测结果", "选择建议与具体人群和场景绑定"],
        },
        "场景解决型": {
            "title": f"遇到{topic}怎么判断？3 个常见场景的行动清单",
            "goal": "实用指南",
            "angle": "按真实使用场景给出分步骤判断方法",
            "format": "场景短视频或清单图文",
            "cover": "3 个场景，一张判断清单",
            "hook": f"当你遇到这个场景，第一步不是凭感觉：{question}？",
            "structure": [
                "还原评论中最常出现的三个使用场景",
                "每个场景先确认目标、限制条件与标签信息",
                "给出可执行的选择步骤和停止条件",
                "补充特殊人群需要专业核验的边界",
            ],
            "points": ["同一答案不适用于所有场景", "行动建议来自标签与公开信息", "特殊人群优先确认专业意见"],
        },
        "清单推荐型": {
            "title": f"关注{topic}时，先完成这份 5 项检查清单",
            "goal": "清单指南",
            "angle": "把分散问题整理成可逐项核对的选择清单",
            "format": "收藏型图文清单",
            "cover": "做选择前，先核对这 5 项",
            "hook": f"如果你也在问“{question}”，先别跳过这份清单。",
            "structure": ["说明清单适用人群", "逐项解释五个核对维度", "演示如何记录未知信息", "总结何时需要进一步咨询"],
            "points": ["清单帮助提问而非替代结论", "未知信息明确留空", "高风险问题交给专业人士"],
        },
        "知识科普型": {
            "title": f"看懂{topic}：先厘清最容易混淆的 3 个概念",
            "goal": "科普",
            "angle": "用定义、例子与边界回应高频问题",
            "format": "知识卡片或讲解视频",
            "cover": "3 个概念，别再混着看",
            "hook": f"这个问题看似简单，其实混在了一起：{question}？",
            "structure": ["呈现真实问题", "解释三个核心概念", "用场景说明边界", "提供核验来源与复查提示"],
            "points": ["概念清楚后再判断", "例子不替代普遍证据", "结论范围必须与证据一致"],
        },
    }
    spec = variants[strategy]
    topic_text = " ".join([opportunity["name"], opportunity["insight"], question])
    risk = (
        "内容涉及健康、安全或功效判断。发布前请核验权威来源、适用人群和剂量/使用边界；"
        "不替代医生、营养师等专业人士的个体建议。"
        if any(word in topic_text for word in HEALTH_WORDS)
        else "发布前请复核引用来源、产品信息与适用场景，不将个别评论扩展为普遍结论。"
    )
    signal_counts = Counter(signal["type"] for signal in detail["signals"])
    top_signal = signal_counts.most_common(1)[0][0] if signal_counts else "真实评论问题"
    return Brief(
        opportunity_id=opportunity["id"],
        opportunity_name=opportunity["name"],
        strategy=strategy,
        title=spec["title"],
        target_audience=audience,
        user_question=question,
        content_goal=spec["goal"],
        angle=spec["angle"],
        format=spec["format"],
        cover_copy=spec["cover"],
        hook=spec["hook"],
        structure=spec["structure"],
        key_points=spec["points"],
        evidence_comment_ids=[item["comment_id"] for item in evidence],
        evidence_comments=[
            {"id": item["comment_id"], "content": item["content"], "source_platform": item["source_platform"], "like_count": item["like_count"]}
            for item in evidence
        ],
        rationale=(
            f"该机会隙值为 {opportunity['gap_score']}，覆盖 {opportunity['comment_count']} 条评论，"
            f"主要信号为{top_signal}。方案直接回应绑定评论中的问题，不使用外部虚构事实。"
        ),
        risk_notice=risk,
        version=version,
    )
