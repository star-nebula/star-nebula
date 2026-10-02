#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刷新 GitHub 主页 README 的「RedNote 最新笔记」卡片。

用法：
  python scripts/update_xhs_notes.py            # 联网抓取（本地 playwright）+ 渲染
  python scripts/update_xhs_notes.py --render   # 离线：按 assets/xhs/notes.json 重渲染

为什么本地跑而不是 GitHub Actions：Actions 的云端 IP 会触发小红书风控
（验证码/限流），本机跑走正常浏览器环境，风险低。

fetch 流程：playwright 打开小红书主页 → 取最新 3 篇笔记（标题 + 封面）→
封面下载到 assets/xhs/note-N.webp → 写 notes.json → 渲染进 README.md 的
XHS-NOTES:START/END 标记块。渲染完成后自行 git 提交推送。

依赖：fetch 模式需要 playwright（本机 ms-playwright chromium，与
xhs_card/render_deck.py 同款环境）；未装 playwright 时仍可用 --render。
"""
import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "assets" / "xhs"
README = REPO / "README.md"
NOTES_JSON = ASSETS / "notes.json"
PROFILE = "https://www.xiaohongshu.com/user/profile/697dfcf40000000024012702"
MARK_RE = re.compile(r"(<!-- XHS-NOTES:START[^\n]*-->\n)(.*?)(<!-- XHS-NOTES:END -->)", re.S)
N = 3


def fetch_notes():
    """本地 playwright 抓取主页最新 N 篇笔记（标题 + 封面 URL）。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(PROFILE, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        cards = page.eval_on_selector_all(
            "section.note-item",
            """els => els.slice(0, %d).map(c => ({
                 title: c.querySelector('.title, a.title, [class*=title]')?.textContent?.trim()
                        || c.querySelector('img')?.alt || '',
                 cover: c.querySelector('img')?.src || '',
               }))""" % N)
        browser.close()
    return cards


def download(url, dest):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.xiaohongshu.com/",
    })
    data = urllib.request.urlopen(req, timeout=30).read()
    if not (data.startswith(b"RIFF") or data[:3] == b"\xff\xd8\xff" or data[:4] == b"\x89PNG"):
        raise ValueError("返回的不是图片（可能触发风控）: " + url[:60])
    dest.write_bytes(data)


def render(notes, profile=PROFILE):
    """把卡片写进 README 的标记块；无标记时插到页脚分隔线之前。"""
    rows = []
    for n in notes:
        title = n["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rows.append(
            '    <td align="center" width="200">'
            '<a href="%s"><img src="%s" width="180" alt="%s" /></a><br />'
            '<a href="%s"><sub>%s</sub></a></td>'
            % (profile, n["cover"], title, profile, title))
    block = ('<h2 align="center">📝 Latest Notes · RedNote</h2>\n'
             '<div align="center">\n<table>\n  <tr>\n'
             + "\n".join(rows) + '\n  </tr>\n</table>\n</div>')
    readme = README.read_text(encoding="utf-8")
    if MARK_RE.search(readme):
        readme = MARK_RE.sub(lambda m: m.group(1) + block + "\n" + m.group(3) + "\n", readme)
    else:
        i = readme.rfind("---\n\n<div")
        assert i != -1, "README 里既无标记块也无页脚锚点"
        readme = readme[:i] + block + "\n\n" + readme[i:]
    README.write_text(readme, encoding="utf-8", newline="\n")


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    if "--render" in sys.argv:
        data = json.loads(NOTES_JSON.read_text(encoding="utf-8"))
        render(data["notes"], data.get("profile", PROFILE))
    else:
        notes = fetch_notes()
        if len(notes) < N or not all(n.get("cover") for n in notes):
            sys.exit("抓取不完整（可能触发风控/验证码），稍后再试，或用 --render")
        for i, n in enumerate(notes, 1):
            dest = ASSETS / ("note-%d.webp" % i)
            download(n["cover"], dest)
            n["cover"] = "assets/xhs/note-%d.webp" % i
        NOTES_JSON.write_text(json.dumps(
            {"profile": PROFILE, "updated": datetime.date.today().isoformat(), "notes": notes},
            ensure_ascii=False, indent=2), encoding="utf-8")
        render(notes, PROFILE)
    print("README 卡片已更新；记得 git add README.md assets/xhs && git commit && git push")


if __name__ == "__main__":
    main()
