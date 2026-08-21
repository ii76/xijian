from __future__ import annotations

import gradio as gr


def render_import_page() -> dict[str, gr.Component]:
    gr.HTML(
        '<div class="page-head"><div><span>01 · INPUT</span><h1>新建调研</h1>'
        '<p>定义研究范围，并导入匿名评论数据。</p></div></div>'
    )

    gr.HTML('<div class="section-label"><b>调研范围</b><span>带 * 为必填项</span></div>')
    with gr.Row(elem_classes="form-grid"):
        with gr.Column():
            topic = gr.Textbox(label="调研主题 *", placeholder="例如：无糖饮料")
            industry = gr.Dropdown(
                ["食品饮料", "美妆个护", "数码家电", "母婴", "健康", "教育", "其他"],
                label="所属行业 *",
                allow_custom_value=True,
            )
            audience = gr.Textbox(label="目标人群", placeholder="例如：控糖人群、健身人群")
        with gr.Column():
            goals = gr.CheckboxGroup(
                ["科普", "测评", "种草", "品牌传播"], label="内容目标 *"
            )
            platforms = gr.CheckboxGroup(
                ["小红书", "抖音", "B站", "微博", "其他"], label="目标平台"
            )

    gr.HTML('<div class="section-label"><b>评论数据</b><span>请勿上传昵称、头像或主页地址</span></div>')
    with gr.Tabs(elem_classes="source-tabs"):
        with gr.Tab("上传文件"):
            file_input = gr.File(
                label="CSV 或 XLSX，最大 10 MB",
                file_types=[".csv", ".xlsx"],
                type="filepath",
            )
            column = gr.Dropdown(label="评论文本列", interactive=True)
        with gr.Tab("粘贴文本"):
            pasted_text = gr.Textbox(
                label="每行一条评论", lines=9, placeholder="无糖是挺好，但代糖安全吗？"
            )
            parse_text = gr.Button("识别文本")
        with gr.Tab("示例数据"):
            gr.Markdown("使用内置的匿名无糖饮料评论，走同一套清洗流程。")
            demo_button = gr.Button("加载示例", variant="primary")

    import_status = gr.Markdown("尚未导入评论。", elem_classes="status-line")
    preview = gr.Dataframe(
        headers=["评论内容", "来源平台", "点赞数"],
        datatype=["str", "str", "number"],
        label="前 10 条预览",
        interactive=False,
        wrap=True,
    )
    with gr.Row(elem_classes="command-bar"):
        start_button = gr.Button("校验并清洗", variant="primary", size="lg")
    return {
        "topic": topic,
        "industry": industry,
        "goals": goals,
        "platforms": platforms,
        "audience": audience,
        "file_input": file_input,
        "column": column,
        "pasted_text": pasted_text,
        "parse_text": parse_text,
        "demo_button": demo_button,
        "import_status": import_status,
        "preview": preview,
        "start_button": start_button,
    }
