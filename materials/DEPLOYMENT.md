# ModelScope 创空间部署

## 文件准备

- 启动入口：`app.py`
- Python 依赖：`requirements.txt`
- 测试依赖：`requirements-dev.txt`（部署不需要安装）
- 容器配置：`Dockerfile`
- 服务监听：`0.0.0.0:7860`
- 可写目录：`exports/`、`data/`

## 创建与发布

1. 登录 ModelScope，创建创空间。
2. 选择 Gradio SDK 或 Docker；本项目两种方式都已准备，Docker 更便于固定 Python 环境。
3. 将项目文件推送到创空间仓库。
4. 发布前在项目根目录运行 `python scripts/check_deploy_layout.py`。
5. 在创空间密钥设置中配置可选的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
6. 不配置 Key 时直接使用无糖饮料预计算示例。
7. 构建完成后检查首页、示例、证据、Brief 和 Markdown 下载。

不使用 Git 推送、需要手动上传时，先运行：

```bash
python scripts/build_modelscope_package.py
```

解压生成的 `ModelScope-创空间部署包.zip`，将解压后的全部内容上传到仓库根目录。不能只上传 `app.py`，也不能直接把 ZIP 文件作为项目源码上传；上传后必须能在仓库文件列表中看到 `models/`、`pages/`、`services/`、`static/`、`data/` 和 `prompts/`。

## 环境变量

| 名称 | 必需 | 默认值 |
|---|---|---|
| `GRADIO_SERVER_NAME` | 否 | `0.0.0.0` |
| `GRADIO_SERVER_PORT` | 否 | `7860` |
| `LLM_API_KEY` | 否 | 空，本地降级 |
| `LLM_BASE_URL` | 否 | OpenAI 兼容地址 |
| `LLM_MODEL` | 否 | `gpt-4o-mini` |
| `LLM_TIMEOUT` | 否 | `45` |
| `LLM_MAX_RETRIES` | 否 | `2` |

## 发布后检查

- 首次访问无报错；
- 无 Key 时示例完整可用；
- 连续运行示例 5 次；
- Chrome 和 Edge 各运行一次；
- 下载 Markdown 后检查标题、结构和评论证据；
- 确认页面和日志不出现 API Key。

## 常见启动错误

### 仓库缺少 requirements.txt

如果构建日志出现：

```text
/home/studio_service/PROJECT/requirements.txt does not exist, skip pip install_requirements.
```

说明创空间实际克隆到的仓库根目录没有 `requirements.txt`。平台会跳过项目依赖安装，并直接使用预装环境；这可能产生 Gradio 与 Hugging Face Hub 的版本冲突。

重新发布前确认以下文件位于仓库根目录，而不是外层文件夹或本地未上传目录：

- `app.py`
- `requirements.txt`
- `models/`
- `pages/`
- `services/`
- `static/`
- `data/`

本项目要求 `gradio==4.44.1` 与 `huggingface-hub==0.36.2`。安装日志应出现项目 `requirements.txt` 的安装过程，不应再出现 `skip pip install_requirements`。

### HfFolder 导入失败

如果日志出现：

```text
ImportError: cannot import name 'HfFolder' from 'huggingface_hub'
```

说明旧版 Gradio 与过新的 Hugging Face Hub 被混装。不要只在创空间终端临时安装单个包；确保根目录 `requirements.txt` 已上传并触发完整重建。若平台预装环境仍覆盖依赖，改用项目提供的 Dockerfile 创建 Docker 创空间。

日志中的 `ms-agent` 缺少可选包、`google-genai` 与 `websockets` 冲突是平台预装环境警告，不是本次启动失败的直接堆栈；真正的失败位置以最后一个 Python traceback 为准。

### Signals 导入失败

如果日志出现：

```text
ImportError: cannot import name 'Signals' from 'signal' (/home/studio_service/PROJECT/signal.py)
```

说明创空间仓库根目录存在业务文件 `signal.py`，覆盖了 Python 自带的同名模块。AnyIO 需要标准库中的 `signal.Signals`，却错误加载了项目文件，因此 Gradio 无法启动。

在创空间仓库中删除根目录的 `signal.py`，并确认业务模型只位于 `models/signal_model.py`；代码导入应保持为 `from models.signal_model import ...`。如果远端有 `__pycache__/signal*.pyc`，一并删除或触发全新构建。上传时必须保留 `models/` 目录层级，不能把目录内文件平铺到仓库根目录。

发布前可运行：

```bash
python scripts/check_deploy_layout.py
```

检查脚本会拦截缺少关键文件、目录层级错误，以及根目录 Python 文件与标准库重名的问题。

### models 包不存在

如果日志出现：

```text
ModuleNotFoundError: No module named 'models'
```

说明远端已经更新了 `app.py`，但仓库根目录没有同步上传 `models/` 文件夹。只更新入口文件会让代码版本不完整；应删除远端不完整文件后，使用部署包一次性上传全部目录。`models/__init__.py` 和 `models/signal_model.py` 必须同时存在。
