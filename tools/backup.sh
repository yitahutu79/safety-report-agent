#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
backup_file="backups/report-data-$(date +%Y%m%d-%H%M%S).tar.gz"
docker compose exec -T report-workbench tar -C /app/data -czf - . > "$backup_file"
printf '数据备份已保存：%s\n' "$backup_file"
printf '备份前请暂停使用并等待任务完成；配置和密钥需另行备份。\n'
