#!/usr/bin/env python3
"""refresh_official.py — Stage 12 子模块 M1.3 (公众号文章).

wx biz-articles 拉本地缓存的公众号推送 → 按来源 + 主题聚合.
"群里 0 公众号 share = 真情报源在订阅号"的 N=1 发现驱动.

Output → ROOT/official.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDED_RE = re.compile(r'扑克|德州|poker|博彩|赌', re.IGNORECASE)


def wx(args, timeout=20):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="YYYY-MM-DD start date")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    since = args.since or (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"[official] biz-articles -n {args.limit} since {since}…", file=sys.stderr)

    t0 = time.time()
    arts = wx(["biz-articles", "-n", str(args.limit), "--since", since])
    if not isinstance(arts, list):
        arts = arts.get("articles", []) if isinstance(arts, dict) else []

    arts = [a for a in arts
            if not EXCLUDED_RE.search((a.get("title") or "") + (a.get("digest") or "") + (a.get("account") or ""))]

    by_source = Counter((a.get("account") or "?")[:30] for a in arts)
    by_day = Counter((a.get("recv_time_str") or a.get("time") or "")[:10] for a in arts)

    titles = " ".join(a.get("title", "") for a in arts)
    tokens = re.findall(r'[一-鿿]{2,8}|[A-Za-z]{3,}', titles)
    common_filter = {"公众号", "推送", "原文", "图文", "原创", "继续阅读", "公司", "发布", "通知"}
    keyword_freq = Counter(t for t in tokens if t not in common_filter)

    arts.sort(key=lambda a: a.get("timestamp", 0), reverse=True)

    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since, "window_days": args.days,
        "n_articles": len(arts), "n_sources": len(by_source),
        "elapsed_sec": round(time.time() - t0, 2),
        "top_sources": [{"account": s, "n": n} for s, n in by_source.most_common(20)],
        "by_day": [{"date": d, "n": n} for d, n in sorted(by_day.items(), reverse=True)[:14]],
        "top_keywords": [{"keyword": k, "n": n} for k, n in keyword_freq.most_common(30)],
        "articles": [
            {"title": (a.get("title") or "?")[:120],
             "digest": (a.get("digest") or "")[:200],
             "account": a.get("account", "?"),
             "time": a.get("recv_time_str") or a.get("time", ""),
             "timestamp": a.get("timestamp", 0),
             "url": a.get("url", "")}
            for a in arts[:50]
        ],
    }
    out = os.path.join(ROOT, "official.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[official] ✓ {payload['elapsed_sec']}s · {len(arts)} 文章 · {len(by_source)} 公众号", file=sys.stderr)
    print(f"[official] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
