"""Create or refresh the Windows development environment."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / "Scripts" / "python.exe"


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("此初始化程序仅用于 Windows。")
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("Windows 协同开发环境统一使用 Python 3.13。")

    if not VENV_PYTHON.exists():
        print(f"正在使用 Python {sys.version.split()[0]} 创建项目环境……", flush=True)
        run(sys.executable, "-m", "venv", str(VENV))
    else:
        print("检测到已有 .venv，将检查并更新项目依赖。", flush=True)

    run(str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip")
    run(str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements-dev.txt")
    run(
        str(VENV_PYTHON),
        "-c",
        "import pypdf, PIL, pypdfium2, qdrant_client, langgraph; "
        "import safety_report.server; print('Windows 运行依赖检查通过。')",
    )
    print("\n初始化完成。以后双击“启动工作台-Windows.cmd”即可使用。", flush=True)


if __name__ == "__main__":
    main()
