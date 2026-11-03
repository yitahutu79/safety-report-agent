#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ "$#" -ne 1 ]; then
  printf '用法：sh tools/restore.sh 备份文件路径\n' >&2
  exit 1
fi
if [ ! -f "$1" ]; then
  printf '备份文件不存在\n' >&2
  exit 1
fi
# 仅恢复到空实例，防止覆盖已有项目。
docker compose exec -T report-workbench python -c 'from pathlib import Path; import sys; sys.exit(1 if list(Path("/app/data").iterdir()) else 0)' || {
  printf '目标数据目录非空，已停止恢复。请使用新的空实例。\n' >&2
  exit 1
}
docker compose exec -T report-workbench tar -C /app/data -xzf - < "$1"
docker compose restart report-workbench
printf '恢复完成，请核对项目和附件。\n'
