#!/bin/zsh
set -eu
project_root="${0:A:h}"
service_label="local.safety-report-agent"
python_bin="$project_root/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3 || true)"
fi
if [[ -z "$python_bin" ]]; then
  print '未找到 Python 3，请联系管理员安装运行环境。'
  read '?按回车关闭窗口'
  exit 1
fi
if ! /bin/launchctl list "$service_label" >/dev/null 2>&1; then
  /bin/launchctl submit -l "$service_label" -o /private/tmp/safety-report-agent.stdout.log -e /private/tmp/safety-report-agent.stderr.log -- "$python_bin" "$project_root/tools/run_workbench.py"
fi
"$python_bin" - <<'CHECK'
import time
import urllib.request
for attempt in range(50):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=1) as response:
            if response.status == 200:
                break
    except OSError:
        time.sleep(0.2)
else:
    raise SystemExit('启动失败，请查看 /private/tmp/safety-report-agent.stderr.log')
CHECK
/usr/bin/open 'http://127.0.0.1:8765'
print '工作台已在后台运行，此窗口可以关闭。退出系统或重启后，请再次双击启动。'
