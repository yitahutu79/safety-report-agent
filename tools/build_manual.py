#!/usr/bin/env python3
"""Build the offline manual from its single Markdown source.

Install requirements-dev.txt, then run: python tools/build_manual.py
Use --check to detect an out-of-date HTML manual without writing files.
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path
import re

import markdown
from markdown.extensions.toc import slugify_unicode

ROOT = Path(__file__).resolve().parents[1]
CSS = '\n:root{--ink:#203b33;--muted:#6b7e74;--green:#17634f;--line:#dfe7e1;--paper:#fff;--bg:#f4f6f3}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:30px}body{margin:0;font:15px/1.9 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:var(--bg)}a{color:var(--green);text-decoration:none}a:hover{text-decoration:underline}.wrap{max-width:1180px;margin:auto;padding:40px 32px 60px}.hero{border-bottom:1px solid var(--line);padding:20px 0 30px;margin-bottom:30px}.eyebrow{font-size:11px;letter-spacing:3px;color:var(--muted)}h1{font-size:32px;line-height:1.5;margin:12px 0;font-weight:650}.subtitle{color:var(--muted);margin:0}.hero-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:24px}.button{display:inline-block;padding:10px 20px;background:var(--green);color:white;border-radius:7px;border:1px solid var(--green);font:inherit;font-size:13px;cursor:pointer}.button.secondary{background:transparent;color:var(--green);border-color:#bdcdc2}.hero small{display:block;color:var(--muted);margin-top:12px;font-size:12px}.layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:36px;align-items:start}nav{position:sticky;top:28px;padding-right:18px}nav strong{font-size:12px;font-weight:500;color:var(--muted);letter-spacing:2px;display:block;margin:0 0 15px}nav a{display:block;color:#5f7869;font-size:12px;padding:9px 0;border-bottom:1px solid #e6ece6;line-height:1.7}article{background:var(--paper);padding:32px 40px;border:1px solid var(--line);border-radius:10px;min-width:0}p{margin:0 0 16px}h2{font-size:23px;margin:38px 0 18px;font-weight:600;border-top:1px solid var(--line);padding-top:30px}h3{font-size:17px;margin:28px 0 14px;font-weight:600}ol{padding-left:25px;margin:12px 0 22px}li{padding-left:5px;margin:8px 0}code{font:12px/1.8 ui-monospace,SFMono-Regular,Menlo,"PingFang SC",monospace;background:#eff4ef;padding:3px 6px;border-radius:4px;overflow-wrap:anywhere;word-break:break-word}pre{background:#f0f5f0;padding:18px 22px;white-space:pre-wrap;overflow:auto;border-radius:6px;margin:18px 0 23px}pre code{background:transparent;padding:0;font-size:13px}.table-wrap{overflow-x:auto;margin:18px 0 24px}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.9}th,td{border:1px solid var(--line);padding:12px 14px;vertical-align:top;text-align:left}th{background:#edf3ed;font-weight:600}td:first-child{min-width:140px}td code{font-size:11px}footer{text-align:center;font-size:11px;color:#89998d;margin-top:30px}.route{font-size:12px;color:var(--muted);overflow-wrap:anywhere}button:focus-visible,a:focus-visible{outline:3px solid #81a88e;outline-offset:3px}@media(max-width:850px){.wrap{padding:25px 18px}.layout{display:block}nav{position:static;padding:0;margin-bottom:25px;display:flex;gap:8px;flex-wrap:wrap}nav strong{width:100%;margin-bottom:5px}nav a{border:1px solid var(--line);border-radius:5px;padding:6px 10px;font-size:11px}article{padding:22px}h1{font-size:27px}h2{font-size:21px}.route{font-size:11px}}@media print{@page{size:A4;margin:18mm 16mm}body{background:white;font-size:10pt;line-height:1.75}.wrap{padding:0;max-width:none}.hero{padding:0 0 14px;margin-bottom:16px}.eyebrow{font-size:8pt}h1{font-size:21pt}.subtitle{font-size:10pt}.hero-actions,nav,.hero small,footer{display:none}.layout{display:block}article{border:0;padding:0;border-radius:0}h2{font-size:15pt;margin:22px 0 12px;padding-top:16px;break-after:avoid}h3{font-size:11.5pt;margin:18px 0 9px;break-after:avoid}p,li{orphans:3;widows:3}table{font-size:9pt}thead{display:table-header-group}tr{break-inside:avoid}th,td{padding:6px 8px}code{font-size:8pt}pre{break-inside:avoid;padding:10px 14px}a{color:inherit}.table-wrap{overflow:visible}td:first-child{min-width:0}.route{font-size:8pt}}\nnav{max-height:calc(100vh - 56px);overflow-y:auto}nav ul{list-style:none;padding:0;margin:0}nav li{margin:0;padding:0}nav .toc a{font-size:12px}@media print{nav{display:none}}'


def render_manual() -> str:
    source = (ROOT / "操作手册.md").read_text(encoding="utf-8")
    converter = markdown.Markdown(extensions=["tables", "toc", "fenced_code", "sane_lists"], extension_configs={"toc": {"toc_depth": "2", "slugify": slugify_unicode}})
    body = converter.convert(source)
    body = re.sub(r"<h1>.*?</h1>\s*", "", body, count=1, flags=re.S)
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    date = re.search(r"最后更新：(.*?)。", source).group(1)
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>安全设施设计报告工作台 操作手册</title><style>{CSS}</style></head>
<body><div class="wrap"><header class="hero"><span class="eyebrow">SAFETY REPORT · USER GUIDE</span>
<h1>安全设施设计报告工作台<br>操作手册</h1>
<p class="subtitle">最后更新：{html.escape(date)} · 与操作手册.md同步生成 · 可离线阅读</p>
<div class="hero-actions"><a class="button" href="http://127.0.0.1:8765" target="_blank" rel="noopener">打开已启动的工作台 ↗</a>
<button class="button secondary" type="button" onclick="window.print()">打印或另存为 PDF</button></div>
<small>先按手册启动程序，再打开工作台。浏览器查找可用 Ctrl/Command+F。</small></header>
<div class="layout"><nav aria-label="手册目录"><strong>操作目录</strong>{converter.toc}</nav><article>{body}</article></div>
<footer>最后更新：{html.escape(date)} · 正文来源：操作手册.md</footer></div></body></html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify HTML matches Markdown without writing")
    args = parser.parse_args()
    target = ROOT / "操作手册.html"
    output = render_manual()
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != output:
            parser.exit(1, "操作手册.html未同步，请运行 python tools/build_manual.py\n")
        print("操作手册 Markdown / HTML 内容同步检查通过")
    else:
        target.write_text(output, encoding="utf-8")
        print("已从操作手册.md生成操作手册.html")


if __name__ == "__main__":
    main()
