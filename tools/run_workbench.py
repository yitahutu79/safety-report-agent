from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
# 本机启动也读取一次环境文件；页面保存的模型配置仍优先按任务选择。
env_path = ROOT / '.env'
if env_path.is_file():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if key in {'APP_PASSWORD', 'LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY', 'LLM_JSON_MODE', 'AMAP_WEB_KEY', 'COOKIE_SECURE', 'CJK_FONT'}:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
from safety_report.server import main

if __name__ == "__main__":
    main()
