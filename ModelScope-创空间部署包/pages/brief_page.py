from __future__ import annotations

import gradio as gr


BRIEF_COUNT = 3


def render_brief_page() -> dict[str, object]:
    heading = gr.HTML(
        '<div class="empty-state">从机会总览或详情页选择“生成内容 Brief”。</div>'
    )
    service_notice = gr.Markdown()
    with gr.Row(elem_classes="command-bar brief-command-bar"):
        generate_button = gr.Button("生成 3 份 Brief", variant="primary", interactive=False)
        export_button = gr.Button("导出 Markdown", interactive=False)
        export_file = gr.File(label="Markdown 报告", visible=False)
    action_status = gr.Markdown()
    cards = []
    for index in range(BRIEF_COUNT):
        with gr.Group(visible=False, elem_classes="brief-card-shell") as group:
            content = gr.HTML()
            with gr.Row():
                regenerate = gr.Button("重新生成此方案")
                copy_title = gr.Button("复制标题")
                copy_full = gr.Button("复制完整 Brief")
        cards.append(
            {
                "group": group,
                "content": content,
                "regenerate": regenerate,
                "copy_title": copy_title,
                "copy_full": copy_full,
            }
        )
    return {
        "heading": heading,
        "service_notice": service_notice,
        "generate_button": generate_button,
        "export_button": export_button,
        "export_file": export_file,
        "action_status": action_status,
        "cards": cards,
    }
