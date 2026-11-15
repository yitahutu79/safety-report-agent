"""Start and stop the source workbench as an isolated Windows background process."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RUNTIME = DATA / ".runtime"
LOGS = DATA / "logs"
PID_FILE = RUNTIME / "windows-workbench.pid"
LOG_FILE = LOGS / "windows-workbench.log"
URL = "http://127.0.0.1:8765"


def service_ready() -> bool:
    try:
        with urllib.request.urlopen(URL + "/", timeout=1) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def process_image(pid: int) -> Path | None:
    """Return the executable path for a Windows process without extra packages."""
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    query_name = kernel32.QueryFullProcessImageNameW
    query_name.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    query_name.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not query_name(handle, 0, buffer, ctypes.byref(size)):
            return None
        return Path(buffer.value)
    finally:
        close_handle(handle)


def recorded_process_is_ours(pid: int) -> bool:
    image = process_image(pid)
    if image is None:
        return False
    try:
        return str(image.resolve()).casefold() == str(Path(sys.executable).resolve()).casefold()
    except OSError:
        return str(image).casefold() == str(Path(sys.executable)).casefold()


def remove_pid_file() -> None:
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def start() -> int:
    if service_ready():
        print("工作台已经在运行，正在打开浏览器。")
        webbrowser.open(URL)
        return 0

    old_pid = read_pid()
    if old_pid and recorded_process_is_ours(old_pid):
        print(f"检测到工作台进程 {old_pid}，但页面尚未就绪。请先运行停止入口后再试。")
        return 1
    remove_pid_file()

    RUNTIME.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with LOG_FILE.open("ab") as log:
        child = subprocess.Popen(
            [sys.executable, str(ROOT / "tools" / "run_workbench.py")],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=flags,
            env=environment,
        )
    PID_FILE.write_text(str(child.pid), encoding="ascii")

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if child.poll() is not None:
            break
        if service_ready():
            print(f"工作台已启动：{URL}")
            print(f"运行日志：{LOG_FILE}")
            webbrowser.open(URL)
            return 0
        time.sleep(0.25)

    if child.poll() is None:
        child.terminate()
    remove_pid_file()
    print("工作台启动失败。请查看日志：")
    print(LOG_FILE)
    return 1


def stop() -> int:
    pid = read_pid()
    if pid is None:
        if service_ready():
            print("检测到8765端口上有服务，但它不是由Windows启动入口记录的进程。")
            print("为避免误停其他程序，请关闭启动该服务的终端窗口。")
            return 1
        print("工作台当前未运行。")
        return 0
    if not recorded_process_is_ours(pid):
        remove_pid_file()
        if service_ready():
            print("进程记录已失效，但8765端口仍有服务；为避免误停，没有结束该进程。")
            return 1
        print("工作台当前未运行，已清理过期的进程记录。")
        return 0

    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    remove_pid_file()
    for _ in range(30):
        if not service_ready():
            print("工作台后台服务已停止。")
            return 0
        time.sleep(0.1)
    if result.returncode != 0:
        print(result.stdout or result.stderr)
    print("停止操作未完成，请检查任务管理器和运行日志。")
    return 1


def status() -> int:
    if service_ready():
        print(f"工作台正在运行：{URL}")
        return 0
    print("工作台当前未运行。")
    return 1


def main() -> None:
    if os.name != "nt":
        raise SystemExit("此工具仅用于 Windows。")
    parser = argparse.ArgumentParser(description="Windows工作台进程管理")
    parser.add_argument("action", choices=("start", "stop", "status"))
    args = parser.parse_args()
    raise SystemExit({"start": start, "stop": stop, "status": status}[args.action]())


if __name__ == "__main__":
    main()
