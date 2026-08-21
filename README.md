# 隙见

隙见是一款基于真实评论证据的 AI 内容机会发现与选题决策工具。当前代码完成前四个阶段：评论数据闭环、机会发现、可追溯核心界面，以及完整 Brief 生成与稳定演示能力。

## 本地启动

要求 Python 3.10 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python app.py
```

打开终端显示的本地地址，默认通常为 `http://127.0.0.1:7860`。

## 测试

```bash
pytest -q
```

## ModelScope 部署

项目根目录已提供 `Dockerfile`，默认监听 `0.0.0.0:7860`。创空间仅需安装 `requirements.txt`；`LLM_API_KEY` 等密钥通过平台环境变量配置，不配置时使用内置无糖饮料示例。

上传前运行 `python scripts/check_deploy_layout.py`，确认关键文件、业务包目录和 Python 模块命名均适合部署。

部署步骤、发布后检查和比赛材料位于 [materials/DEPLOYMENT.md](materials/DEPLOYMENT.md)。

真实 API Key 只能写入本地 `.env`，不要提交到仓库。可按 `.env.example` 配置兼容接口；未配置时自动使用本地分析。
