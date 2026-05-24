#!/usr/bin/env python3
"""refresh_mentions.py — 真 @我 计数 via wx search.

Replaces "has unread groups" proxy with real @-mention count.
Reads SELF_IDS + AT_QUERIES from config.json.

Output → ROOT/mentions.json with 4 windows {1d, 3d, 7d, 30d}.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wx(args, timeout=15):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout)


def _unwrap(d):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("matches", "results", "messages", "items"):
            if k in d and isinstance(d[k], list):
                return d[k]
    return []


def search_at(at_queries: list[str], self_ids: tuple, since_str: str, limit: int = 500):
    """合并多个 query 的结果, 去重 by (chat, timestamp, sender), 过滤自己."""
    seen, out = set(), []
    for q in at_queries:
        try:
            items = _unwrap(wx(["search", q, "--since", since_str, "-n", str(limit)]))
        except Exception:
            continue
        for m in items:
            sender = (m.get("sender") or "").strip()
            if any(sid in sender for sid in self_ids):
                continue
            key = (m.get("chat", ""), m.get("timestamp", 0), sender)
            if key in seen:
                continue
            seen.add(key)
            out.append(m)
    return out


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import self_ids as _sids, at_queries as _aqs, windows as _windows  # noqa

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=_windows().get("mentions_days", 7),
                    help="primary window for at_me KPI")
    args = ap.parse_args()

    SELF_IDS = _sids()
    AT_QUERIES = _aqs()
    if not AT_QUERIES:
        print("❌ config.json 缺 at_queries. 例: ['@YourNick']", file=sys.stderr)
        sys.exit(1)
    if not SELF_IDS:
        print("⚠ config.json 缺 self_ids → 自己 @ 自己会被算进 mentions", file=sys.stderr)

    print(f"[mentions] queries={AT_QUERIES} · windows 1d/3d/7d/30d…", file=sys.stderr)
    t0 = time.time()
    windows = {}
    for d in (1, 3, 7, 30):
        since = (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d")
        n = len(search_at(AT_QUERIES, SELF_IDS, since))
        windows[f"{d}d"] = n
        print(f"  past {d}d: {n}", file=sys.stderr)

    since_main = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    items = search_at(AT_QUERIES, SELF_IDS, since_main, limit=500)
    items.sort(key=lambda m: m.get("timestamp", 0), reverse=True)
    by_chat = Counter((m.get("chat") or "?")[:30] for m in items)
    by_sender = Counter((m.get("sender") or "?")[:20] for m in items)

    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since_main, "window_days": args.days, "windows": windows,
        "n_total": len(items), "n_unique_groups": len(by_chat),
        "by_group": [{"group": g, "n": n} for g, n in by_chat.most_common(20)],
        "by_sender": [{"sender": s, "n": n} for s, n in by_sender.most_common(20)],
        "recent": [
            {"chat": (m.get("chat") or "?")[:30],
             "sender": (m.get("sender") or "?")[:20],
             "content": (m.get("content") or "")[:200],
             "time": m.get("time", ""),
             "timestamp": m.get("timestamp", 0)}
            for m in items[:25]
        ],
        "elapsed_sec": round(time.time() - t0, 2),
    }
    out_path = os.path.join(ROOT, "mentions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[mentions] ✓ {payload['elapsed_sec']}s · primary({args.days}d)={payload['n_total']} "
          f"· spread across {payload['n_unique_groups']} groups", file=sys.stderr)
    print(f"[mentions] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
