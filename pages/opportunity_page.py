from __future__ import annotations

import gradio as gr


MAX_OPPORTUNITY_CARDS = 8


def render_opportunity_page() -> dict[str, object]:
    summary = gr.HTML(
        '<div class="empty-state">完成评论清洗并运行分析后，这里将显示内容机会。</div>'
    )
    with gr.Row(equal_height=False):
        signal_distribution = gr.HTML()
        weak_signals = gr.HTML()
    gr.HTML('<div class="section-label"><b>筛选与排序</b><span>结果即时更新</span></div>')
    with gr.Row(elem_classes="filter-toolbar"):
        sort_by = gr.Dropdown(
            ["隙值从高到低", "评论数从高到低"],
            value="隙值从高到低",
            label="排序",
        )
        priority = gr.Dropdown(
            ["全部优先级", "优先策划", "值得关注", "补充观察"],
            value="全部优先级",
            label="优先级",
        )
        signal_filter = gr.CheckboxGroup(
            ["需求矛盾", "高频疑问", "观点分歧", "对比需求", "隐藏场景"],
            label="信号类型",
            scale=3,
        )

    gr.HTML('<div class="section-label"><b>内容机会</b><span>正式机会至少绑定 3 条评论证据</span></div>')

    cards: list[dict[str, gr.Component]] = []
    for _ in range(MAX_OPPORTUNITY_CARDS):
        with gr.Group(visible=False, elem_classes="opportunity-card-shell") as group:
            content = gr.HTML()
            with gr.Row():
                detail_button = gr.Button("查看证据", variant="primary")
                brief_button = gr.Button("生成 Brief")
        cards.append(
            {
                "group": group,
                "content": content,
                "detail_button": detail_button,
                "brief_button": brief_button,
            }
        )
    empty = gr.HTML("", visible=False)
    return {
        "summary": summary,
        "signal_distribution": signal_distribution,
        "weak_signals": weak_signals,
        "sort_by": sort_by,
        "priority": priority,
        "signal_filter": signal_filter,
        "cards": cards,
        "empty": empty,
    }
