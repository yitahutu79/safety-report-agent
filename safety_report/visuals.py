import json
import os
from datetime import datetime, timezone
from pathlib import Path
import textwrap
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape


def draw_flow(steps, directory):
    if not isinstance(steps, list) or not 2 <= len(steps) <= 20 or any(not isinstance(s, str) or not s.strip() or len(s) > 80 for s in steps):
        raise ValueError('请提供 2 到 20 个工艺步骤，每步 1 到 80 字')
    directory = Path(directory)
    height = 120 * len(steps) + 40
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{height}" viewBox="0 0 720 {height}"><rect width="720" height="{height}" fill="white"/>'
    for i, step in enumerate(steps):
        y = 30 + i * 120
        svg += f'<rect x="100" y="{y}" width="520" height="82" rx="4" fill="#f1f5f9" stroke="#334155"/>'
        lines = textwrap.wrap(step, 25)
        for j, line in enumerate(lines):
            svg += f'<text x="360" y="{y + 28 + j * 21}" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#172b3f">{escape(line)}</text>'
        if i < len(steps) - 1:
            svg += f'<path d="M360 {y + 82}V{y + 110}m-6 -6l6 6 6 -6" stroke="#334155" fill="none" stroke-width="2"/>'
    svg += '</svg>'
    (directory / 'flow.svg').write_text(svg, encoding='utf-8')
    # SVG 可直接下载；安装 Pillow 后同时输出可嵌入 Word 的 PNG。
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {'file': 'flow.svg', 'embedded': False, 'message': '已生成 SVG；安装 Pillow 和中文字体后可生成 Word 内嵌 PNG'}
    candidates = [os.environ.get('CJK_FONT', ''), '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  '/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Light.ttc']
    font_path = next((p for p in candidates if p and Path(p).is_file()), None)
    if not font_path:
        return {'file': 'flow.svg', 'embedded': False, 'message': '已生成 SVG；未找到中文字体，未生成 PNG'}
    image = Image.new('RGB', (720, height), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 19)
    for i, step in enumerate(steps):
        y = 30 + i * 120
        draw.rounded_rectangle((100, y, 620, y + 82), radius=4, fill='#f1f5f9', outline='#334155', width=2)
        draw.multiline_text((360, y + 41), '\n'.join(textwrap.wrap(step, 25)), font=font, fill='#172b3f', anchor='mm', align='center', spacing=3)
        if i < len(steps) - 1:
            draw.line((360, y + 82, 360, y + 110), fill='#334155', width=2)
            draw.line((354, y + 104, 360, y + 110, 366, y + 104), fill='#334155', width=2)
    image.save(directory / 'flow.png')
    return {'file': 'flow.png', 'embedded': True, 'message': '已生成流程图，下一次生成报告时嵌入 Word'}


def geocode(address):
    if not isinstance(address, str) or not 2 <= len(address) <= 200:
        raise ValueError('请输入完整地址')
    key = os.environ.get('AMAP_WEB_KEY')
    if not key:
        raise ValueError('管理员尚未配置高德地图 Web 服务密钥 AMAP_WEB_KEY')
    params = urllib.parse.urlencode({'key': key, 'address': address})
    with urllib.request.urlopen('https://restapi.amap.com/v3/geocode/geo?' + params, timeout=25) as response:
        data = json.load(response)
    if data.get('status') != '1':
        raise ValueError('地图地址查询失败，请管理员检查地图权限和配额')
    return [{'address': r.get('formatted_address'), 'location': r.get('location'), 'level': r.get('level')}
            for r in data.get('geocodes', [])]


def static_map(location, address, directory):
    try:
        lng, lat = map(float, location.split(','))
        if not -180 <= lng <= 180 or not -90 <= lat <= 90:
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError('地图坐标须为经度,纬度，并采用高德 GCJ-02 坐标')
    key = os.environ.get('AMAP_WEB_KEY')
    if not key:
        raise ValueError('管理员尚未配置地图服务密钥')
    params = urllib.parse.urlencode({'key': key, 'location': location, 'zoom': '14', 'size': '750*500', 'scale': '2', 'markers': 'mid,,A:' + location})
    with urllib.request.urlopen('https://restapi.amap.com/v3/staticmap?' + params, timeout=30) as response:
        data = response.read(8_000_001)
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) > 8_000_000:
        raise ValueError('地图服务未返回 PNG，请检查静态地图权限')
    directory = Path(directory)
    (directory / 'map.png').write_bytes(data)
    (directory / 'map.json').write_text(json.dumps({'provider': '高德地图', 'address': address, 'location': location,
        'coordinate_system': 'GCJ-02', 'zoom': 14, 'captured_at': datetime.now(timezone.utc).isoformat(),
        'source': 'https://lbs.amap.com/api/webservice/guide/api/staticmaps'}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'file': 'map.png', 'message': '地图已保存；坐标点不能用于确定厂界、间距或规范符合性'}
