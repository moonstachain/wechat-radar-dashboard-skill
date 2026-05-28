#!/usr/bin/env python3
"""refresh_unified.py — Stage 12 子模块 M2.2 (跨源同人物归一).

纯 Python 字符串匹配 (不烧 LLM, 更稳定):
  · 收集 4 source 人名: 群 top_senders + 私聊 chat + 公众号 account + @ 你的人
  · 按前 2-3 个中文字 fingerprint 归一
  · 找出在 ≥ 2 source 出现的 canonical name → unified node

Reads SELF_IDS from config.json (for filtering out 你自己).
Output → ROOT/unified.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDED_RE = re.compile(r'扑克|德州|poker|博彩|赌', re.IGNORECASE)

PREFIX_RE = re.compile(r'^[A-Za-z@\[【\(]{0,3}[\s\-_·]*')
COMMON_NICK_SUFFIX = re.compile(
    r'[\s\-_·@\.]+(\w*(公司|工作室|笔记|读书|社区|创业营|私董会|顾问|经理|总监|CEO|CTO))[\s"")\]】]*$',
    re.IGNORECASE,
)


def fingerprint(name: str) -> str | None:
    if not name or EXCLUDED_RE.search(name):
        return None
    s = name.strip()
    s = PREFIX_RE.sub('', s).strip()
    s = COMMON_NICK_SUFFIX.sub('', s).strip()
    m = re.match(r'^([一-鿿]{2,3})', s)
    if not m:
        m2 = re.match(r'^([A-Za-z]{3,10})', s)
        return m2.group(1).lower() if m2 else None
    return m.group(1)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import self_ids as _sids  # noqa

    SELF_IDS = _sids()
    t0 = time.time()
    sources_data = []

    # 1. Group top_senders
    sp = os.path.join(ROOT, "stats.json")
    if os.path.exists(sp):
        ss = json.load(open(sp, encoding="utf-8"))
        for s in ss.get("top_senders_cross_group", [])[:50]:
            name = (s.get("name") or "").strip()
            if any(sid in name for sid in SELF_IDS): continue
            sources_data.append({"name": name, "source": "群",
                                  "where": s.get("where") or "",
                                  "extra": f"{s.get('n')}条 / {s.get('extra','')}",
                                  "n": s.get("n", 0)})

    # 2. Private partners
    pp = os.path.join(ROOT, "private.json")
    if os.path.exists(pp):
        d = json.load(open(pp, encoding="utf-8"))
        for p in (d.get("active_recent", []) + d.get("overdue_to_me", [])):
            name = (p.get("chat") or "").strip()
            if any(sid in name for sid in SELF_IDS): continue
            sources_data.append({"name": name, "source": "私", "where": "1-on-1",
                                  "extra": f"unread={p.get('unread',0)}", "n": 1})

    # 3. Official accounts
    op = os.path.join(ROOT, "official.json")
    if os.path.exists(op):
        d = json.load(open(op, encoding="utf-8"))
        for s in d.get("top_sources", [])[:30]:
            name = (s.get("account") or "").strip()
            sources_data.append({"name": name, "source": "公", "where": "公众号",
                                  "extra": f"{s.get('n')}文", "n": s.get("n", 0)})

    # 4. @ senders
    mp = os.path.join(ROOT, "mentions.json")
    if os.path.exists(mp):
        d = json.load(open(mp, encoding="utf-8"))
        for s in d.get("by_sender", [])[:20]:
            name = (s.get("sender") or "").strip()
            if any(sid in name for sid in SELF_IDS): continue
            sources_data.append({"name": name, "source": "@", "where": "@你",
                                  "extra": f"@你 {s.get('n')} 次", "n": s.get("n", 0)})

    print(f"[unified] gathered {len(sources_data)} appearances", file=sys.stderr)

    by_fp = defaultdict(list)
    for item in sources_data:
        fp = fingerprint(item["name"])
        if not fp: continue
        item["_fp"] = fp
        by_fp[fp].append(item)

    unified = []
    for fp, items in by_fp.items():
        source_types = set(it["source"] for it in items)
        if len(source_types) < 2: continue
        unique_names = list({it["name"] for it in items})
        unified.append({
            "canonical": fp, "n_sources": len(source_types),
            "source_types": sorted(source_types),
            "n_appearances": len(items),
            "names_seen": unique_names,
            "appearances": [{"name": it["name"], "source": it["source"],
                              "where": it["where"], "extra": it["extra"]}
                             for it in items],
        })

    unified.sort(key=lambda x: (x["n_sources"], x["n_appearances"]), reverse=True)

    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_total_appearances": len(sources_data),
        "n_fingerprints": len(by_fp),
        "n_unified": len(unified),
        "elapsed_sec": round(time.time() - t0, 2),
        "unified": unified[:50],
    }
    out = os.path.join(ROOT, "unified.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[unified] ✓ {payload['elapsed_sec']}s · {len(sources_data)} appearances · "
          f"{len(unified)} cross-source nodes", file=sys.stderr)
    print(f"[unified] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
