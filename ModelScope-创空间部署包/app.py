from __future__ import annotations

import html
import os
import tempfile
from functools import partial
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "xijian-matplotlib"))

import gradio as gr

from models.signal_model import Signal
from models.task import Task
from pages.analysis_page import EMPTY_PROGRESS, render_analysis_page
from pages.brief_page import BRIEF_COUNT, render_brief_page
from pages.detail_page import render_detail_page
from pages.home import render_home
from pages.import_page import render_import_page
from pages.opportunity_page import MAX_OPPORTUNITY_CARDS, render_opportunity_page
from services.brief_service import generate_briefs, regenerate_brief, render_brief_html
from services.analytics_service import record_event
from services.clean_service import clean_comments
from services.cluster_service import cluster_signals
from services.demo_service import load_demo_analysis, load_demo_briefs
from services.export_service import export_markdown
from services.import_service import (
    ImportDataError,
    import_summary,
    inspect_file,
    materialize_records,
    parse_pasted_text,
    preview_rows,
)
from services.llm_service import LLMConfigurationError, OpenAICompatibleClient
from services.score_service import score_opportunities
from services.signal_service import analyze_comments, retry_failed_batches
from services.storage_service import load_briefs, load_latest_analysis, save_analysis, save_briefs
from services.view_service import (
    build_detail,
    filter_opportunities,
    render_detail_header,
    render_detail_insight,
    render_evidence,
    render_opportunity_card,
    render_overview_summary,
    render_score_detail,
    render_signal_distribution,
    render_weak_signals,
)


ROOT = Path(__file__).resolve().parent
DEMO_FILE = ROOT / "data" / "demo" / "sugar_free_comments.csv"
CSS = (ROOT / "static" / "css" / "theme.css").read_text(encoding="utf-8")


def _import_status(payload: dict, selected_column: str | None = None) -> str:
    summary = import_summary(payload, selected_column)
    column_text = summary["comment_column"] or "未识别"
    platform_text = "有" if summary["has_platform"] else "无"
    likes_text = "有" if summary["has_likes"] else "无"
    warning = " 样本少于 20 条，可继续，但结论可信度会较低。" if summary["row_count"] < 20 else ""
    return (
        f"**已读取 {summary['source_name']}** · 原始 {summary['row_count']} 条 · "
        f"异常行 {summary['abnormal_count']} 条 · 评论列 `{column_text}` · "
        f"平台字段：{platform_text} · 点赞字段：{likes_text}.{warning}"
    )


def _load_payload(payload: dict) -> tuple:
    columns = payload.get("columns", [])
    selected = payload.get("detected_comment_column")
    if selected:
        status = _import_status(payload, selected)
        preview = preview_rows(payload, selected)
    else:
        status = "未自动识别评论列，请从下拉框手动选择。"
        preview = []
    return gr.Dropdown(choices=columns, value=selected), preview, status, payload


def handle_file(file_path: str | None) -> tuple:
    if not file_path:
        return gr.Dropdown(choices=[], value=None), [], "尚未选择文件。", {}
    try:
        result = _load_payload(inspect_file(file_path))
        record_event("import_succeeded", metadata={"source": "file"})
        return result
    except ImportDataError as exc:
        record_event("import_failed", metadata={"source": "file"})
        return gr.Dropdown(choices=[], value=None), [], f"导入失败：{exc}", {}


def handle_pasted_text(text: str) -> tuple:
    try:
        result = _load_payload(parse_pasted_text(text))
        record_event("import_succeeded", metadata={"source": "pasted_text"})
        return result
    except ImportDataError as exc:
        record_event("import_failed", metadata={"source": "pasted_text"})
        return gr.Dropdown(choices=[], value=None), [], f"导入失败：{exc}", {}


def load_demo_payload() -> dict:
    payload = inspect_file(DEMO_FILE)
    payload["source_type"] = "demo"
    return payload


def handle_demo() -> tuple:
    record_event("demo_started", metadata={"source": "built_in"})
    record_event("import_succeeded", metadata={"source": "demo"})
    payload = load_demo_payload()
    return _load_payload(payload)


def handle_column_change(column: str | None, payload: dict) -> tuple:
    if not column or not payload:
        return [], "请选择评论文本列。"
    try:
        return preview_rows(payload, column), _import_status(payload, column)
    except ImportDataError as exc:
        return [], f"列读取失败：{exc}"


def _quality_markdown(summary: dict) -> str:
    notes: list[str] = []
    if summary["sample_warning"]:
        notes.append("样本少于 20 条，允许继续，但后续结论需标记低样本风险。")
    if summary["quality_warning"]:
        notes.append("有效率低于 50%，建议补充更完整的评论数据。")
    if summary["all_duplicate"]:
        notes.append("全部评论完全重复，已阻止进入分析，请更换数据。")
    note_text = "  \n".join(f"- {note}" for note in notes) or "- 数据质量满足第一阶段要求。"
    return f"""
### 评论质量摘要

| 原始评论 | 去重后 | 有效评论 | 无效评论 | 完全重复 | 数据有效率 |
|---:|---:|---:|---:|---:|---:|
| {summary['raw_count']} | {summary['unique_count']} | {summary['valid_count']} | {summary['invalid_count']} | {summary['duplicate_count']} | {summary['effective_rate']:.1%} |

{note_text}
"""


def _progress_html(step: int, message: str, failed: bool = False) -> str:
    width = max(0, min(100, round(step / 6 * 100)))
    steps = ("清洗评论", "提取表达", "识别信号", "聚合机会", "计算隙值", "机会摘要")
    labels = []
    for index, label in enumerate(steps, start=1):
        state = "done" if index < step else "active" if index == step else ""
        if failed and index == step:
            state = "failed"
        labels.append(f'<span class="{state}" data-step="{index}">{index} {label}</span>')
    return f"""
<div class="progress-shell">
  <div class="progress-head"><b>{message}</b><span>{width}%</span></div>
  <div class="progress-track"><i class="{'failed' if failed else ''}" style="width:{width}%"></i></div>
  <div class="step-grid">{''.join(labels)}</div>
</div>
"""


def handle_clean(
    topic: str,
    industry: str | None,
    goals: list[str],
    platforms: list[str],
    audience: str,
    column: str | None,
    payload: dict,
) -> tuple:
    missing = []
    if not (topic or "").strip():
        missing.append("调研主题")
    if not industry:
        missing.append("所属行业")
    if not goals:
        missing.append("内容目标")
    if missing:
        return _clean_error(f"请填写{'、'.join(missing)}。")

    try:
        raw_records = materialize_records(payload, column)
    except ImportDataError as exc:
        return _clean_error(str(exc))

    task = Task(
        topic=topic.strip(),
        industry=industry,
        content_goals=goals,
        platforms=platforms or [],
        target_audience=(audience or "").strip(),
    )
    comments, summary = clean_comments(raw_records, task.id)
    rows = [
        [
            comment.id,
            comment.content,
            comment.source_platform,
            comment.duplicate_count,
            "有效" if comment.valid else "无效",
            comment.invalid_reason or "",
        ]
        for comment in comments[:100]
    ]
    ready = summary.analysis_ready
    status = (
        f"清洗完成，任务 `{task.id}` 已生成。可以开始六步分析。"
        if ready
        else "清洗完成，但当前数据未通过进入分析的条件。"
    )
    clean_payload = {
        "comments": [comment.to_dict() for comment in comments],
        "quality": summary.to_dict(),
        "source_type": payload.get("source_type", "unknown"),
        "source_name": payload.get("source_name", ""),
    }
    save_analysis({"task": task.to_dict(), **clean_payload, "signals": [], "opportunities": []})
    record_event("task_created", task.id, metadata={"industry": industry})
    return (
        status,
        _quality_markdown(summary.to_dict()),
        _progress_html(1, "评论清洗完成") if ready else EMPTY_PROGRESS,
        rows,
        task.to_dict(),
        clean_payload,
        gr.Tabs(selected="analysis"),
        gr.Button(interactive=ready),
        gr.Button(interactive=ready and payload.get("source_type") == "demo"),
        gr.Button(visible=False),
        gr.Button(visible=False),
        "",
        {},
        {},
        "",
        "",
        [],
    )


def _clean_error(message: str) -> tuple:
    return (
        f"无法校验：{message}",
        "",
        EMPTY_PROGRESS,
        [],
        {},
        {},
        gr.Tabs(selected="analysis"),
        gr.Button(interactive=False),
        gr.Button(interactive=False),
        gr.Button(visible=False),
        gr.Button(visible=False),
        "",
        {},
        {},
        "",
        "",
        [],
    )


def _configured_client() -> OpenAICompatibleClient | None:
    try:
        return OpenAICompatibleClient.from_env()
    except LLMConfigurationError:
        return None


def _build_analysis_state(
    signal_result,
    opportunities,
    clean_payload: dict,
    task_payload: dict,
    mode: str | None = None,
) -> dict:
    task = dict(task_payload)
    task["status"] = "completed" if signal_result.processed_comment_ids else "failed"
    return {
        "mode": mode or signal_result.mode,
        "signals": [
            signal.to_dict() if isinstance(signal, Signal) else signal
            for signal in signal_result.signals
        ],
        "processed_comment_ids": list(signal_result.processed_comment_ids),
        "failed_batches": [
            batch.to_dict() if hasattr(batch, "to_dict") else batch
            for batch in signal_result.failed_batches
        ],
        "opportunities": [
            opportunity.to_dict() if hasattr(opportunity, "to_dict") else opportunity
            for opportunity in opportunities
        ],
        "comments": clean_payload["comments"],
        "quality": clean_payload["quality"],
        "task": task,
    }


def handle_analysis(clean_payload: dict, task_payload: dict):
    if not clean_payload or not clean_payload.get("quality", {}).get("analysis_ready"):
        yield _analysis_error("当前数据未通过分析条件。", task_payload)
        return
    processing_task = dict(task_payload)
    processing_task["status"] = "processing"
    yield (
        "正在提取用户表达…",
        _progress_html(2, "提取用户表达"),
        "",
        gr.Button(visible=False),
        gr.Button(visible=False),
        {},
        processing_task,
        gr.Button(interactive=False),
    )
    try:
        comments = clean_payload["comments"]
        client = _configured_client()
        signal_result = analyze_comments(
            comments,
            client=client,
            topic_hint=task_payload.get("topic", ""),
        )
        yield (
            f"已识别 {len(signal_result.signals)} 个内容信号。",
            _progress_html(3, "识别五类内容信号"),
            _failed_batch_text(signal_result.failed_batches),
            gr.Button(visible=bool(signal_result.failed_batches)),
            gr.Button(visible=False),
            {},
            processing_task,
            gr.Button(interactive=False),
        )
        opportunities = cluster_signals(signal_result.signals, task_payload["id"], client=client)
        yield (
            f"已聚合 {len(opportunities)} 个候选机会。",
            _progress_html(4, "聚合相似内容机会"),
            _failed_batch_text(signal_result.failed_batches),
            gr.Button(visible=bool(signal_result.failed_batches)),
            gr.Button(visible=False),
            {},
            processing_task,
            gr.Button(interactive=False),
        )
        scored = score_opportunities(opportunities, comments)
        yield (
            "评论数、覆盖率与隙值已由程序计算。",
            _progress_html(5, "统计并计算隙值"),
            _failed_batch_text(signal_result.failed_batches),
            gr.Button(visible=bool(signal_result.failed_batches)),
            gr.Button(visible=False),
            {},
            processing_task,
            gr.Button(interactive=False),
        )
        state = _build_analysis_state(
            signal_result, scored, clean_payload, task_payload
        )
        save_analysis(state)
        record_event(
            "analysis_completed",
            task_payload.get("id", ""),
            metadata={"mode": state.get("mode", ""), "opportunity_count": len(scored)},
        )
        formal, weak = filter_opportunities(state["opportunities"])
        yield (
            f"分析完成：{len(formal)} 个内容机会，{len(weak)} 个低频弱信号。",
            _progress_html(6, "机会摘要生成完成"),
            _failed_batch_text(signal_result.failed_batches),
            gr.Button(visible=bool(signal_result.failed_batches)),
            gr.Button(visible=True),
            state,
            state["task"],
            gr.Button(interactive=False),
        )
    except Exception as exc:
        record_event("analysis_failed", task_payload.get("id", ""), metadata={"step": 2})
        yield _analysis_error(f"分析失败：{str(exc)[:240]}", task_payload, step=2)


def _analysis_error(message: str, task_payload: dict, step: int = 1) -> tuple:
    task = dict(task_payload or {})
    task["status"] = "failed"
    return (
        message,
        _progress_html(step, "处理失败", failed=True),
        "已停止当前任务，不会无限加载。可直接重新分析，无需重新上传。",
        gr.Button(visible=False),
        gr.Button(visible=True),
        {},
        task,
        gr.Button(interactive=False),
    )


def _failed_batch_text(failed_batches) -> str:
    if not failed_batches:
        return "所有批次处理成功。"
    details = "；".join(
        f"批次 {batch.batch_index + 1}: {batch.error}"
        if hasattr(batch, "batch_index")
        else f"批次 {batch['batch_index'] + 1}: {batch['error']}"
        for batch in failed_batches
    )
    return f"部分批次失败，已保留成功结果。{details}"


def handle_retry(clean_payload: dict, task_payload: dict, state: dict) -> tuple:
    failed = state.get("failed_batches", []) if state else []
    if not failed:
        return (
            "没有需要重试的失败批次。",
            _progress_html(6, "任务已完成"),
            "",
            gr.Button(visible=False),
            gr.Button(visible=True),
            state,
            state.get("task", task_payload),
            gr.Button(interactive=False),
        )
    client = _configured_client()
    retried = retry_failed_batches(
        clean_payload["comments"],
        failed,
        client=client,
        topic_hint=task_payload.get("topic", ""),
    )
    signal_map = {signal["id"]: Signal(**signal) for signal in state.get("signals", [])}
    for signal in retried.signals:
        signal_map[signal.id] = signal
    merged_signals = list(signal_map.values())
    opportunities = score_opportunities(
        cluster_signals(merged_signals, task_payload["id"], client=client),
        clean_payload["comments"],
    )

    class MergedResult:
        signals = merged_signals
        processed_comment_ids = sorted(
            set(state.get("processed_comment_ids", []))
            | set(retried.processed_comment_ids)
        )
        failed_batches = retried.failed_batches
        mode = retried.mode

    merged_state = _build_analysis_state(
        MergedResult, opportunities, clean_payload, task_payload
    )
    save_analysis(merged_state)
    return (
        "失败批次重试完成。",
        _progress_html(6, "机会摘要生成完成"),
        _failed_batch_text(retried.failed_batches),
        gr.Button(visible=bool(retried.failed_batches)),
        gr.Button(visible=True),
        merged_state,
        merged_state["task"],
        gr.Button(interactive=False),
    )


def handle_demo_precomputed(clean_payload: dict, task_payload: dict) -> tuple:
    if clean_payload.get("source_type") != "demo":
        return _analysis_error("当前数据不是内置示例，不能读取无糖饮料预计算结果。", task_payload)
    if task_payload.get("topic") != "无糖饮料":
        return _analysis_error("预计算结果仅适用于内置无糖饮料示例。", task_payload)
    try:
        payload = load_demo_analysis()
        task = dict(task_payload)
        task["status"] = "completed"
        opportunities = []
        for opportunity in payload["opportunities"]:
            item = dict(opportunity)
            item["task_id"] = task["id"]
            opportunities.append(item)
        state = {
            "mode": "precomputed_demo",
            "signals": payload["signals"],
            "processed_comment_ids": payload["processed_comment_ids"],
            "failed_batches": [],
            "opportunities": opportunities,
            "comments": clean_payload["comments"],
            "quality": clean_payload["quality"],
            "task": task,
        }
        save_analysis(state)
        record_event(
            "analysis_completed",
            task.get("id", ""),
            metadata={"mode": "precomputed_demo", "opportunity_count": len(opportunities)},
        )
        formal, weak = filter_opportunities(opportunities)
        return (
            f"已读取示例结果：{len(formal)} 个内容机会，{len(weak)} 个弱信号。",
            _progress_html(6, "示例预计算结果已加载"),
            "示例结果加载成功，可点击“重新分析”运行完整流程。",
            gr.Button(visible=False),
            gr.Button(visible=True),
            state,
            task,
            gr.Button(interactive=False),
        )
    except Exception as exc:
        return _analysis_error(f"示例结果读取失败：{exc}", task_payload)


def render_opportunity_view(
    state: dict,
    sort_by: str = "隙值从高到低",
    signal_types: list[str] | None = None,
    priority: str = "全部优先级",
) -> tuple:
    if not state or not state.get("opportunities"):
        return _empty_opportunity_view()
    all_formal, weak = filter_opportunities(state["opportunities"])
    filtered, _ = filter_opportunities(
        state["opportunities"], sort_by, signal_types or [], priority
    )
    visible = filtered[:MAX_OPPORTUNITY_CARDS]
    output: list[object] = [
        render_overview_summary(state, len(all_formal), len(weak)),
        render_signal_distribution(state.get("signals", [])),
        render_weak_signals(weak),
        {"opportunity_ids": [item["id"] for item in visible]},
    ]
    for index in range(MAX_OPPORTUNITY_CARDS):
        if index < len(visible):
            output.extend(
                [
                    gr.Group(visible=True),
                    gr.HTML(
                        value=render_opportunity_card(
                            visible[index], state.get("comments", [])
                        )
                    ),
                ]
            )
        else:
            output.extend([gr.Group(visible=False), gr.HTML(value="")])
    output.extend(
        [
            gr.HTML(
                value='<div class="empty-state">当前筛选下没有内容机会。</div>',
                visible=not visible,
            ),
            gr.Tabs(selected="opportunities"),
        ]
    )
    return tuple(output)


def _empty_opportunity_view() -> tuple:
    output: list[object] = [
        '<div class="empty-state">尚无分析结果。</div>',
        "",
        "",
        {"opportunity_ids": []},
    ]
    for _ in range(MAX_OPPORTUNITY_CARDS):
        output.extend([gr.Group(visible=False), gr.HTML(value="")])
    output.extend([gr.HTML(value="", visible=False), gr.Tabs(selected="analysis")])
    return tuple(output)


def open_opportunity(index: int, view_state: dict, analysis_state: dict) -> tuple:
    ids = view_state.get("opportunity_ids", []) if view_state else []
    if index >= len(ids):
        return ("<div>机会不存在。</div>", "", "", gr.Dropdown(value="全部证据"), "", "", gr.Tabs())
    opportunity_id = ids[index]
    task_id = analysis_state.get("task", {}).get("id", "")
    record_event("opportunity_clicked", task_id, opportunity_id)
    record_event("evidence_opened", task_id, opportunity_id)
    detail = build_detail(opportunity_id, analysis_state)
    return (
        render_detail_header(detail),
        render_score_detail(detail),
        render_detail_insight(detail),
        gr.Dropdown(value="全部证据"),
        render_evidence(detail["evidence"]),
        opportunity_id,
        gr.Tabs(selected="detail"),
    )


def handle_evidence_filter(
    evidence_filter: str, opportunity_id: str, analysis_state: dict
) -> str:
    if not opportunity_id or not analysis_state:
        return ""
    return render_evidence(
        build_detail(opportunity_id, analysis_state, evidence_filter)["evidence"]
    )


def select_brief_from_card(
    index: int, view_state: dict, analysis_state: dict
) -> tuple:
    ids = view_state.get("opportunity_ids", []) if view_state else []
    opportunity_id = ids[index] if index < len(ids) else ""
    return _open_brief(opportunity_id, analysis_state)


def _select_brief(opportunity_id: str, analysis_state: dict) -> tuple:
    opportunity = next(
        (item for item in analysis_state.get("opportunities", []) if item["id"] == opportunity_id),
        None,
    )
    if not opportunity:
        return "", "未选择有效内容机会。", gr.Tabs()
    return (
        opportunity_id,
        f"### 已选择：{opportunity['name']}\n\n当前机会 ID：`{opportunity_id}`。",
        gr.Tabs(selected="brief"),
    )


def _open_brief(opportunity_id: str, analysis_state: dict) -> tuple:
    opportunity = next(
        (
            item
            for item in analysis_state.get("opportunities", [])
            if item["id"] == opportunity_id
        ),
        None,
    )
    if not opportunity:
        return _empty_brief_selection("未选择有效内容机会。")
    task_id = analysis_state.get("task", {}).get("id", "")
    briefs = load_briefs(task_id, opportunity_id)
    status = "已恢复此前保存的 3 份 Brief。"
    if len(briefs) != BRIEF_COUNT and analysis_state.get("mode") == "precomputed_demo":
        briefs = load_demo_briefs().get(opportunity_id, [])
        status = "已读取无糖饮料示例预生成 Brief。"
    if len(briefs) != BRIEF_COUNT:
        try:
            briefs = generate_briefs(opportunity_id, analysis_state)
            save_briefs(task_id, opportunity_id, briefs)
            status = "已根据当前机会和真实评论证据生成 3 份 Brief。"
        except Exception as exc:
            return _empty_brief_selection(f"Brief 生成失败：{str(exc)[:200]}")
    record_event("brief_generated", task_id, opportunity_id, {"brief_count": len(briefs)})
    return (
        opportunity_id,
        briefs,
        _brief_heading(opportunity),
        _ai_service_notice(analysis_state),
        gr.Button(interactive=True),
        gr.Button(interactive=True),
        status,
        *_brief_card_updates(briefs),
        gr.Tabs(selected="brief"),
    )


def handle_generate_briefs(opportunity_id: str, analysis_state: dict) -> tuple:
    try:
        briefs = generate_briefs(opportunity_id, analysis_state)
        save_briefs(analysis_state["task"]["id"], opportunity_id, briefs)
        return (
            briefs,
            "已重新生成 3 份差异化 Brief。",
            gr.Button(interactive=True),
            *_brief_card_updates(briefs),
        )
    except Exception as exc:
        return ([], f"生成失败：{str(exc)[:200]}。页面复制功能仍可使用。", gr.Button(interactive=False), *_brief_card_updates([]))


def handle_regenerate_brief(index: int, opportunity_id: str, analysis_state: dict, briefs: list[dict]) -> tuple:
    try:
        updated = regenerate_brief(opportunity_id, analysis_state, briefs, index)
        save_briefs(analysis_state["task"]["id"], opportunity_id, updated)
        return updated, f"方案 {index + 1} 已重新生成，其余方案保持不变。", *_brief_card_updates(updated)
    except Exception as exc:
        return briefs, f"重新生成失败：{str(exc)[:200]}。原方案已保留。", *_brief_card_updates(briefs)


def handle_export_report(analysis_state: dict, briefs: list[dict]) -> tuple:
    try:
        path = export_markdown(analysis_state, briefs)
        record_event(
            "markdown_exported",
            analysis_state.get("task", {}).get("id", ""),
            briefs[0].get("opportunity_id", "") if briefs else "",
            {"brief_count": len(briefs)},
        )
        return gr.File(value=str(path), visible=True), f"Markdown 报告已生成：`{path.name}`"
    except Exception as exc:
        return gr.File(visible=False), f"导出失败：{str(exc)[:200]}。页面复制功能仍可使用。"


def restore_latest_view() -> tuple:
    state = load_latest_analysis()
    if not state or not state.get("opportunities"):
        view = list(_empty_opportunity_view())
        view[-1] = gr.Tabs(selected="home")
        return ({}, {}, {}, *view)
    clean = {"comments": state.get("comments", []), "quality": state.get("quality", {})}
    view = list(render_opportunity_view(state))
    view[-1] = gr.Tabs(selected="home")
    return (state.get("task", {}), clean, state, *view)


def start_new_task() -> gr.Tabs:
    record_event("task_created", metadata={"stage": "opened"})
    return gr.Tabs(selected="import")


def record_brief_copy(opportunity_id: str, analysis_state: dict, copy_type: str) -> None:
    record_event(
        "brief_copied",
        analysis_state.get("task", {}).get("id", "") if analysis_state else "",
        opportunity_id or "",
        {"copy_type": copy_type},
    )


def _brief_heading(opportunity: dict) -> str:
    return f"""
<div class="brief-heading"><div><div class="eyebrow">对应内容机会 · {html.escape(opportunity['id'])}</div>
<h2>{html.escape(opportunity['name'])}</h2><p>{html.escape(opportunity['insight'])}</p></div>
<div class="brief-score"><b>{opportunity['gap_score']}</b><span>隙值</span></div></div>
"""


def _ai_service_notice(state: dict) -> str:
    if os.getenv("LLM_API_KEY", "").strip():
        return "AI 服务已配置；当前 Brief 使用受约束生成器，结果仅引用已绑定证据。"
    if state.get("task", {}).get("topic") == "无糖饮料":
        return "**未配置 `LLM_API_KEY`。当前 AI 服务不可用，已使用可离线演示的无糖饮料证据生成方案。**"
    return "**未配置 `LLM_API_KEY`，已切换到本地受约束生成器；不会上传评论数据。**"


def _brief_card_updates(briefs: list[dict]) -> tuple:
    output = []
    for index in range(BRIEF_COUNT):
        if index < len(briefs):
            output.extend([gr.Group(visible=True), gr.HTML(value=render_brief_html(briefs[index], index))])
        else:
            output.extend([gr.Group(visible=False), gr.HTML(value="")])
    return tuple(output)


def _empty_brief_selection(message: str) -> tuple:
    return (
        "", [], f'<div class="empty-state">{html.escape(message)}</div>', "",
        gr.Button(interactive=False), gr.Button(interactive=False), message,
        *_brief_card_updates([]), gr.Tabs(selected="brief"),
    )


with gr.Blocks(
    title="隙见 · 内容机会发现",
    css=CSS
) as demo:
    imported_state = gr.State({})
    task_state = gr.State({})
    clean_state = gr.State({})
    analysis_state = gr.State({})
    view_state = gr.State({})
    current_opportunity_state = gr.State("")
    brief_opportunity_state = gr.State("")
    brief_state = gr.State([])

    gr.HTML(
        """
        <header class="app-header">
          <div class="app-brand">
            <img class="app-brand-logo" src="/file=static/images/logo-large.png" alt="隙见 XIJIAN">
          </div>
          <div class="app-brand-tag">评论证据工作台</div>
        </header>
        """
    )
    with gr.Tabs(selected="home", elem_id="main-tabs") as main_tabs:
        with gr.Tab("首页", id="home"):
            home = render_home()
        with gr.Tab("新建调研", id="import"):
            importer = render_import_page()
        with gr.Tab("数据校验与分析", id="analysis"):
            analysis = render_analysis_page()
        with gr.Tab("内容机会总览", id="opportunities"):
            opportunity_page = render_opportunity_page()
        with gr.Tab("机会详情", id="detail"):
            detail_page = render_detail_page()
        with gr.Tab("内容 Brief", id="brief"):
            brief_page = render_brief_page()

    home["new_task"].click(start_new_task, outputs=main_tabs)
    home["load_demo"].click(
        handle_demo,
        outputs=[
            importer["column"],
            importer["preview"],
            importer["import_status"],
            imported_state,
        ],
    ).then(
        lambda: (
            "无糖饮料",
            "食品饮料",
            ["科普", "测评"],
            gr.Tabs(selected="import"),
        ),
        outputs=[
            importer["topic"],
            importer["industry"],
            importer["goals"],
            main_tabs,
        ],
    )
    importer["file_input"].change(
        handle_file,
        inputs=importer["file_input"],
        outputs=[
            importer["column"],
            importer["preview"],
            importer["import_status"],
            imported_state,
        ],
    )
    importer["parse_text"].click(
        handle_pasted_text,
        inputs=importer["pasted_text"],
        outputs=[
            importer["column"],
            importer["preview"],
            importer["import_status"],
            imported_state,
        ],
    )
    importer["demo_button"].click(
        handle_demo,
        outputs=[
            importer["column"],
            importer["preview"],
            importer["import_status"],
            imported_state,
        ],
    )
    importer["column"].change(
        handle_column_change,
        inputs=[importer["column"], imported_state],
        outputs=[importer["preview"], importer["import_status"]],
    )
    importer["start_button"].click(
        handle_clean,
        inputs=[
            importer["topic"],
            importer["industry"],
            importer["goals"],
            importer["platforms"],
            importer["audience"],
            importer["column"],
            imported_state,
        ],
        outputs=[
            analysis["analysis_status"],
            analysis["quality"],
            analysis["progress"],
            analysis["cleaned"],
            task_state,
            clean_state,
            main_tabs,
            analysis["next_button"],
            analysis["demo_result_button"],
            analysis["retry_button"],
            analysis["reanalyze_button"],
            analysis["failure_detail"],
            analysis_state,
            view_state,
            current_opportunity_state,
            brief_opportunity_state,
            brief_state,
        ],
    )

    analysis_outputs = [
        analysis["analysis_status"],
        analysis["progress"],
        analysis["failure_detail"],
        analysis["retry_button"],
        analysis["reanalyze_button"],
        analysis_state,
        task_state,
        analysis["next_button"],
    ]
    opportunity_outputs = [
        opportunity_page["summary"],
        opportunity_page["signal_distribution"],
        opportunity_page["weak_signals"],
        view_state,
    ]
    for card in opportunity_page["cards"]:
        opportunity_outputs.extend([card["group"], card["content"]])
    opportunity_outputs.extend([opportunity_page["empty"], main_tabs])
    opportunity_inputs = [
        analysis_state,
        opportunity_page["sort_by"],
        opportunity_page["signal_filter"],
        opportunity_page["priority"],
    ]
    analysis_state.change(
        render_opportunity_view,
        inputs=opportunity_inputs,
        outputs=opportunity_outputs,
    )
    demo.load(
        restore_latest_view,
        outputs=[task_state, clean_state, analysis_state, *opportunity_outputs],
    )

    analysis_event = analysis["next_button"].click(
        handle_analysis,
        inputs=[clean_state, task_state],
        outputs=analysis_outputs,
    )
    analysis_event.then(
        render_opportunity_view,
        inputs=opportunity_inputs,
        outputs=opportunity_outputs,
    )
    demo_event = analysis["demo_result_button"].click(
        handle_demo_precomputed,
        inputs=[clean_state, task_state],
        outputs=analysis_outputs,
    )
    demo_event.then(
        render_opportunity_view,
        inputs=opportunity_inputs,
        outputs=opportunity_outputs,
    )
    retry_event = analysis["retry_button"].click(
        handle_retry,
        inputs=[clean_state, task_state, analysis_state],
        outputs=analysis_outputs,
    )
    retry_event.then(
        render_opportunity_view,
        inputs=opportunity_inputs,
        outputs=opportunity_outputs,
    )
    reanalysis_event = analysis["reanalyze_button"].click(
        handle_analysis,
        inputs=[clean_state, task_state],
        outputs=analysis_outputs,
    )
    reanalysis_event.then(
        render_opportunity_view,
        inputs=opportunity_inputs,
        outputs=opportunity_outputs,
    )

    for component in (
        opportunity_page["sort_by"],
        opportunity_page["signal_filter"],
        opportunity_page["priority"],
    ):
        component.change(
            render_opportunity_view,
            inputs=opportunity_inputs,
            outputs=opportunity_outputs,
        )

    detail_outputs = [
        detail_page["header"],
        detail_page["score_detail"],
        detail_page["insight_detail"],
        detail_page["evidence_filter"],
        detail_page["evidence"],
        current_opportunity_state,
        main_tabs,
    ]
    brief_selection_outputs = [
        brief_opportunity_state,
        brief_state,
        brief_page["heading"],
        brief_page["service_notice"],
        brief_page["generate_button"],
        brief_page["export_button"],
        brief_page["action_status"],
    ]
    for card in brief_page["cards"]:
        brief_selection_outputs.extend([card["group"], card["content"]])
    brief_selection_outputs.append(main_tabs)
    for index, card in enumerate(opportunity_page["cards"]):
        card["detail_button"].click(
            partial(open_opportunity, index),
            inputs=[view_state, analysis_state],
            outputs=detail_outputs,
        )
        card["brief_button"].click(
            partial(select_brief_from_card, index),
            inputs=[view_state, analysis_state],
            outputs=brief_selection_outputs,
        )

    detail_page["evidence_filter"].change(
        handle_evidence_filter,
        inputs=[
            detail_page["evidence_filter"],
            current_opportunity_state,
            analysis_state,
        ],
        outputs=detail_page["evidence"],
    )
    detail_page["back_button"].click(
        lambda: gr.Tabs(selected="opportunities"), outputs=main_tabs
    )
    detail_page["brief_button"].click(
        _open_brief,
        inputs=[current_opportunity_state, analysis_state],
        outputs=brief_selection_outputs,
    )

    brief_card_outputs = []
    for card in brief_page["cards"]:
        brief_card_outputs.extend([card["group"], card["content"]])
    brief_page["generate_button"].click(
        handle_generate_briefs,
        inputs=[brief_opportunity_state, analysis_state],
        outputs=[brief_state, brief_page["action_status"], brief_page["export_button"], *brief_card_outputs],
    )
    for index, card in enumerate(brief_page["cards"]):
        card["regenerate"].click(
            partial(handle_regenerate_brief, index),
            inputs=[brief_opportunity_state, analysis_state, brief_state],
            outputs=[brief_state, brief_page["action_status"], *brief_card_outputs],
        )
        card["copy_title"].click(
            fn=partial(record_brief_copy, copy_type="title"),
            inputs=[brief_opportunity_state, analysis_state],
            js=f"(opportunityId, state) => {{ const text=document.querySelector('#brief-card-{index} h3').textContent; if(globalThis.navigator && globalThis.navigator.clipboard) globalThis.navigator.clipboard.writeText(text); else {{ const area=document.createElement('textarea'); area.value=text; document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove(); }} return [opportunityId, state]; }}",
        )
        card["copy_full"].click(
            fn=partial(record_brief_copy, copy_type="full"),
            inputs=[brief_opportunity_state, analysis_state],
            js=f"(opportunityId, state) => {{ const text=document.querySelector('#brief-card-{index}').innerText; if(globalThis.navigator && globalThis.navigator.clipboard) globalThis.navigator.clipboard.writeText(text); else {{ const area=document.createElement('textarea'); area.value=text; document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove(); }} return [opportunityId, state]; }}",
        )
    brief_page["export_button"].click(
        handle_export_report,
        inputs=[analysis_state, brief_state],
        outputs=[brief_page["export_file"], brief_page["action_status"]],
    )

demo.queue()


if __name__ == "__main__":
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        favicon_path=str(ROOT / "static" / "images" / "favicon.png"),
        allowed_paths=[str(ROOT / "static")],
    )
