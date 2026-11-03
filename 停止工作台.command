#!/bin/zsh
set -eu
service_label="local.safety-report-agent"
if /bin/launchctl list "$service_label" >/dev/null 2>&1; then
  /bin/launchctl remove "$service_label"
  # 等待任务注销完成，避免紧接着启动时与旧任务的退出过程竞争。
  for attempt in {1..50}; do
    if ! /bin/launchctl list "$service_label" >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
  sleep 0.3
  print '工作台后台服务已停止。'
else
  print '工作台当前未运行。'
fi
