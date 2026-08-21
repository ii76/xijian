from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from check_deploy_layout import find_errors


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ModelScope-创空间部署包.zip"
ROOT_FILES = ("app.py", "requirements.txt", "Dockerfile", ".env.example")
RUNTIME_DIRS = ("models", "pages", "services", "static", "data/demo", "prompts")
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def should_include(path: Path) -> bool:
    return not any(part in IGNORED_NAMES for part in path.parts) and path.suffix not in IGNORED_SUFFIXES


def collect_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    for directory in RUNTIME_DIRS:
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file() and should_include(path))
    return sorted(set(files))


def main() -> int:
    errors = find_errors()
    if errors:
        print("部署包生成失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    files = collect_files()
    missing = [str(path.relative_to(ROOT)) for path in files if not path.exists()]
    if missing:
        print("部署包生成失败，缺少文件：")
        for path in missing:
            print(f"- {path}")
        return 1

    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT))

    print(f"ModelScope 部署包已生成：{OUTPUT}")
    print(f"共包含 {len(files)} 个运行文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
