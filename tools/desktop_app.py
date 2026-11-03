"""Desktop launcher: native WebView shell + isolated local report service."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP_NAME = '安全设施设计报告工作台'


def _data_home() -> Path:
    if sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    elif os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or (Path.home() / '.local' / 'share'))
    path = base / 'AnSheZhiBian'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return int(listener.getsockname()[1])


def _server_command(port: int, data_dir: Path) -> list[str]:
    args = ['--server', '--host', '127.0.0.1', '--port', str(port), '--data', str(data_dir)]
    if getattr(sys, 'frozen', False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def _start_service(port: int, data_dir: Path, log_path: Path) -> subprocess.Popen:
    log_file = log_path.open('ab')
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        child = subprocess.Popen(
            _server_command(port, data_dir), stdin=subprocess.DEVNULL,
            stdout=log_file, stderr=subprocess.STDOUT, close_fds=(os.name != 'nt'), **kwargs)
    finally:
        log_file.close()
    url = f'http://127.0.0.1:{port}/api/status'
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if child.poll() is not None:
            break
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return child
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill()
    try:
        details = log_path.read_text(encoding='utf-8', errors='replace')[-3000:]
    except OSError:
        details = ''
    raise RuntimeError('本地服务未能启动。日志位置：' + str(log_path) + ('\n' + details if details else ''))


def _desktop() -> None:
    import webview

    data_dir = _data_home()
    logs = data_dir / 'logs'
    logs.mkdir(exist_ok=True)
    log_path = logs / 'desktop.log'
    logger = logging.getLogger('safety-report-desktop')
    logger.setLevel(logging.INFO)
    logger.addHandler(RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding='utf-8'))
    port = _free_local_port()
    service = _start_service(port, data_dir, logs / 'service.log')
    try:
        webview.create_window(
            APP_NAME, f'http://127.0.0.1:{port}/', width=1440, height=920,
            min_size=(1024, 700), background_color='#f3f6f4')
        webview.start(debug=False)
    except Exception:
        logger.exception('桌面窗口启动失败')
        raise
    finally:
        if service.poll() is None:
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=2)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == '--server':
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from safety_report.server import main as server_main
        server_main()
        return
    try:
        _desktop()
    except Exception as exc:
        # Keep a useful diagnostic for packaged, windowed builds.
        try:
            data_dir = _data_home()
            (data_dir / 'logs').mkdir(exist_ok=True)
            (data_dir / 'logs' / 'startup-error.txt').write_text(str(exc), encoding='utf-8')
        except OSError:
            pass
        raise


if __name__ == '__main__':
    main()
