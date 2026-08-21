from __future__ import annotations

import gradio as gr


EMPTY_PROGRESS = """
<div class="progress-shell">
  <div class="progress-track"><i style="width:0%"></i></div>
  <div class="step-grid">
    <span data-step="1">1 清洗评论</span><span data-step="2">2 提取表达</span><span data-step="3">3 识别信号</span>
    <span data-step="4">4 聚合机会</span><span data-step="5">5 计算隙值</span><span data-step="6">6 机会摘要</span>
  </div>
</div>
"""


def render_analysis_page() -> dict[str, gr.Component]:
    gr.HTML(
        '<div class="page-head"><div><span>02 · ANALYZE</span><h1>数据校验与分析</h1>'
        '<p>先确认数据质量，再运行六步机会分析。</p></div></div>'
    )
    analysis_status = gr.Markdown(
        "导入评论并点击“校验并清洗”后，这里会显示数据质量。",
        elem_classes="status-line",
    )
    quality = gr.Markdown("", elem_classes="quality-summary")
    progress = gr.HTML(EMPTY_PROGRESS)
    with gr.Row(elem_classes="command-bar"):
        next_button = gr.Button("开始分析", variant="primary", interactive=False)
        demo_result_button = gr.Button("读取示例结果", interactive=False)
        retry_button = gr.Button("重试失败批次", visible=False)
        reanalyze_button = gr.Button("重新分析", visible=False)
    failure_detail = gr.Markdown("", elem_classes="status-line")
    gr.HTML('<div class="section-label"><b>标准评论预览</b><span>最多显示前 100 条</span></div>')
    cleaned = gr.Dataframe(
        headers=["评论 ID", "清洗后评论", "来源", "重复次数", "状态", "说明"],
        datatype=["str", "str", "str", "number", "str", "str"],
        label="标准评论预览",
        show_label=False,
        interactive=False,
        wrap=True,
    )
    return {
        "analysis_status": analysis_status,
        "quality": quality,
        "progress": progress,
        "cleaned": cleaned,
        "next_button": next_button,
        "demo_result_button": demo_result_button,
        "retry_button": retry_button,
        "reanalyze_button": reanalyze_button,
        "failure_detail": failure_detail,
    }
