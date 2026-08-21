from __future__ import annotations

import gradio as gr


def render_home() -> dict[str, gr.Component]:
    with gr.Column(elem_classes="hero-shell"):
        gr.HTML(
            """
            <div class="home-intro">
              <div class="hero-eyebrow">评论证据驱动的选题工作台</div>
              <h1 class="hero-title">从真实评论里，<br>判断下一个<span>值得做</span>的选题。</h1>
              <p class="hero-copy">导入评论，识别内容机会，回看证据，并生成可执行 Brief。</p>
            </div>
            <div class="demo-dataset">
              <div class="demo-dataset-mark">DEMO</div>
              <div><b>无糖饮料示例</b><span>54 条匿名评论 · 6 个正式机会 · 18 份预生成 Brief</span></div>
            </div>
            """
        )
        with gr.Row(elem_classes="hero-actions"):
            new_task = gr.Button("新建调研", variant="primary", size="lg")
            load_demo = gr.Button("体验无糖饮料示例", size="lg")
    return {"new_task": new_task, "load_demo": load_demo}
