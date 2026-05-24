#!/usr/bin/env python3
"""refresh_links.py — aggregate real URLs from wx history --type link.

For each group, parse WeChat <appmsg> XML in message `content` to extract
<url>/<title>/<des>/sourcedisplayname.

Output → ROOT/links.json with summary by_category / by_group_top10 / n_real vs n_junk.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wx(args, timeout=30):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout)


URL_RE   = re.compile(r"<url>([^<]+)</url>", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(?:<!\[CDATA\[)?([^<\]]+?)(?:\]\]>)?</title>", re.I | re.S)
DES_RE   = re.compile(r"<des[^>]*>(?:<!\[CDATA\[)?([^<\]]+?)(?:\]\]>)?</des>", re.I | re.S)
SRC_RE   = re.compile(r"<sourcedisplayname>(?:<!\[CDATA\[)?([^<\]]+?)(?:\]\]>)?</sourcedisplayname>", re.I)


def _strip(s):
    return html.unescape((s or "").strip())


# Categorize URLs to surface "real vs junk" (WeChat-internal redirects are junk).
CATEGORIES = [
    (r"mp\.weixin\.qq\.com/s[/?]",      "公众号文章", "📰"),
    (r"mp\.weixin\.qq\.com/mp/waerrpage", "小程序升级", "🚫"),
    (r"finder\.video\.qq\.com|channels\.weixin\.qq\.com", "视频号", "🎬"),
    (r"support\.weixin\.qq\.com",       "WeChat 支持", "🚫"),
    (r"h5\.qzone\.qq\.com",             "QQ 空间", "🚫"),
    (r"wxs\.qq\.com|weixin\.qq\.com/q/", "微信平台", "🚫"),
    (r"github\.com|gitee\.com",         "GitHub/Gitee", "💻"),
    (r"xiaohongshu\.com|xhslink\.com",  "小红书", "📕"),
    (r"douyin\.com|iesdouyin\.com",     "抖音", "🎵"),
    (r"youtube\.com|youtu\.be",         "YouTube", "📺"),
    (r"feishu\.cn|larksuite\.com",      "飞书", "📋"),
    (r"notion\.so|notion\.site",        "Notion", "📝"),
    (r"bilibili\.com|b23\.tv",          "B站", "📺"),
    (r"zhihu\.com",                     "知乎", "💡"),
    (r"twitter\.com|x\.com/",           "X/Twitter", "🐦"),
    (r"openai\.com|anthropic\.com",     "AI 厂商", "🧠"),
]
_CAT_COMPILED = [(re.compile(r, re.I), l, ic) for (r, l, ic) in CATEGORIES]


def classify_url(url):
    for rx, label, icon in _CAT_COMPILED:
        if rx.search(url):
            return label, icon, icon == "🚫"
    return "其他外站", "🌐", False


def parse_link(content):
    if not content or "<url>" not in content:
        return None
    m = URL_RE.search(content)
    if not m:
        return None
    url = _strip(m.group(1))
    if not url.startswith(("http://", "https://")):
        return None
    return {
        "url": url,
        "title":  _strip(TITLE_RE.search(content).group(1)) if TITLE_RE.search(content) else "",
        "des":    _strip(DES_RE.search(content).group(1))   if DES_RE.search(content)   else "",
        "source": _strip(SRC_RE.search(content).group(1))   if SRC_RE.search(content)   else "",
    }


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import windows as _windows  # noqa

    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="YYYY-MM-DD start date")
    ap.add_argument("--days", type=int, default=_windows().get("links_days", 30))
    ap.add_argument("--limit-per-group", type=int, default=200)
    ap.add_argument("--max-groups", type=int, default=200)
    args = ap.parse_args()

    since = args.since or (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    sessions = wx(["sessions", "-n", "500"]).get("sessions", []) or []
    groups = [s for s in sessions if s.get("chat_type") == "group"][:args.max_groups]
    print(f"[links] aggregating {len(groups)} groups since {since}…", file=sys.stderr)

    t0 = time.time()
    links = []
    seen_urls = set()
    failed = []
    n_ok = 0

    for i, g in enumerate(groups):
        chat_key = g.get("username") or g.get("chat") or ""
        chat_name = g.get("chat") or chat_key
        if not chat_key:
            continue
        try:
            h = wx(["history", chat_key, "--type", "link", "--since", since, "-n", str(args.limit_per_group)])
            for m in (h.get("messages") or []):
                parsed = parse_link(m.get("content", ""))
                if not parsed or parsed["url"] in seen_urls:
                    continue
                seen_urls.add(parsed["url"])
                cat_label, cat_icon, is_junk = classify_url(parsed["url"])
                links.append({
                    **parsed,
                    "group": chat_name[:30],
                    "sender": (m.get("sender") or "").strip()[:20],
                    "time": m.get("time", ""),
                    "timestamp": m.get("timestamp", 0),
                    "cat_label": cat_label, "cat_icon": cat_icon, "is_junk": is_junk,
                })
            n_ok += 1
        except Exception as e:
            failed.append({"chat": chat_name, "err": str(e)[:80]})
        if (i + 1) % 10 == 0 or i == len(groups) - 1:
            print(f"  {i+1}/{len(groups)} · {len(links)} URLs · {time.time()-t0:.1f}s",
                  file=sys.stderr)

    links.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    cat_counter = Counter(l["cat_label"] for l in links)
    group_counter = Counter(l["group"] for l in links)
    summary = {
        "by_category": [{"label": l,
                         "icon": next((ic for (_, lb, ic) in CATEGORIES if lb == l), "🌐"),
                         "n": n}
                        for l, n in cat_counter.most_common()],
        "by_group_top10": [{"group": g, "n": n} for g, n in group_counter.most_common(10)],
        "n_junk": sum(1 for l in links if l["is_junk"]),
        "n_real": sum(1 for l in links if not l["is_junk"]),
    }

    elapsed = time.time() - t0
    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since, "window_days": args.days,
        "n_groups": len(groups), "n_groups_ok": n_ok, "n_failed": len(failed),
        "elapsed_sec": round(elapsed, 2),
        "n_links_total": len(links), "n_links_unique": len(seen_urls),
        "summary": summary, "links": links[:200], "failed": failed,
    }
    out_path = os.path.join(ROOT, "links.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[links] ✓ {elapsed:.1f}s · {len(links)} URLs from {n_ok}/{len(groups)} groups · failed={len(failed)}",
          file=sys.stderr)
    print(f"[links] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
