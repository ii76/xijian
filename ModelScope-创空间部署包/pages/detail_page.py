from __future__ import annotations

import gradio as gr

from services.view_service import EVIDENCE_FILTERS


def render_detail_page() -> dict[str, gr.Component]:
    header = gr.HTML('<div class="empty-state">请从内容机会总览选择“查看证据”。</div>')
    with gr.Row(equal_height=False):
        with gr.Column(scale=4, elem_classes="detail-panel"):
            gr.HTML('<div class="section-label"><b>五维评分</b><span>程序计算</span></div>')
            score_detail = gr.HTML()
        with gr.Column(scale=6, elem_classes="detail-panel"):
            gr.HTML('<div class="section-label"><b>机会洞察</b><span>来自关联信号</span></div>')
            insight_detail = gr.HTML()
    with gr.Row(elem_classes="command-bar"):
        back_button = gr.Button("返回机会总览")
        evidence_filter = gr.Dropdown(
            list(EVIDENCE_FILTERS), value="全部证据", label="证据筛选"
        )
        brief_button = gr.Button("生成内容 Brief", variant="primary")
    gr.HTML('<div class="section-label"><b>原始评论证据</b><span>匿名化展示</span></div>')
    evidence = gr.HTML()
    return {
        "header": header,
        "score_detail": score_detail,
        "insight_detail": insight_detail,
        "evidence_filter": evidence_filter,
        "back_button": back_button,
        "brief_button": brief_button,
        "evidence": evidence,
    }
