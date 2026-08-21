from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    "app.py",
    "requirements.txt",
    "models",
    "models/signal_model.py",
    "pages",
    "services",
    "static/css/theme.css",
    "static/images/logo-large.png",
    "data/demo/demo_analysis.json",
    "data/demo/demo_briefs.json",
    "data/demo/sugar_free_comments.csv",
    "prompts/brief_prompt.txt",
    "prompts/cluster_summary.txt",
    "prompts/comment_analysis.txt",
)


def find_errors() -> list[str]:
    errors = [f"缺少部署文件或目录：{path}" for path in REQUIRED_PATHS if not (ROOT / path).exists()]

    for python_file in ROOT.glob("*.py"):
        if python_file.stem in sys.stdlib_module_names:
            errors.append(
                f"根目录文件 {python_file.name} 与 Python 标准库同名，请移动到业务包目录并更新导入路径"
            )

    return errors


def main() -> int:
    errors = find_errors()
    if errors:
        print("部署目录检查失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print("部署目录检查通过：入口、依赖和业务包层级正确。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
