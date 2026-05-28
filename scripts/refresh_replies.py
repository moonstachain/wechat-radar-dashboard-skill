#!/usr/bin/env python3
"""refresh_replies.py — 未回复积压检测 (Stage 10, card 6).

For each group where you got @-ed in the last N days:
  · find your last own-message timestamp in that group
  · if @ to you is more recent than your last reply → 未回复
  · sort by "hours overdue" descending

Reads SELF_IDS + AT_QUERIES from config.json (no hardcoded wxid).

Output → ROOT/replies.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wx(args, timeout=20):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout)


def _unwrap(d):
    if isinstance(d, list): return d
    if isinstance(d, dict):
        for k in ("matches", "results", "messages", "items"):
            if k in d and isinstance(d[k], list): return d[k]
    return []


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import self_ids as _sids, at_queries as _aqs  # noqa

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="how far back to scan for @ you got")
    args = ap.parse_args()

    SELF_IDS = _sids()
    AT_QUERIES = _aqs()
    if not AT_QUERIES:
        print("❌ config.json 缺 at_queries", file=sys.stderr)
        sys.exit(1)

    since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"[replies] scanning @s since {since} for queries {AT_QUERIES}…", file=sys.stderr)

    # Step 1: collect all @-mentions in window, dedup
    seen, items = set(), []
    for q in AT_QUERIES:
        try:
            r = _unwrap(wx(["search", q, "--since", since, "-n", "500"]))
        except Exception:
            continue
        for m in r:
            sender = (m.get("sender") or "").strip()
            if any(sid in sender for sid in SELF_IDS):
                continue
            key = (m.get("chat", ""), m.get("timestamp", 0), sender)
            if key in seen: continue
            seen.add(key)
            items.append(m)

    # Step 2: group by chat, keep most recent @ per chat
    by_chat = {}
    for m in items:
        c = m.get("chat", "")
        ts = m.get("timestamp", 0)
        if c not in by_chat or ts > by_chat[c]["at_ts"]:
            by_chat[c] = {
                "chat": c, "at_ts": ts,
                "at_time": m.get("time", ""),
                "at_sender": (m.get("sender") or "").strip()[:20],
                "at_content": (m.get("content") or "")[:120],
            }
    print(f"[replies] {len(by_chat)} groups had @ in last {args.days}d", file=sys.stderr)

    # Step 3: for each group, find your last own-message timestamp
    overdue = []
    for chat_name, info in by_chat.items():
        try:
            h = _unwrap(wx(["history", chat_name, "--since", since, "-n", "500"]))
        except Exception as e:
            info["err"] = str(e)[:80]
            continue
        my_last_ts = 0
        for m in h:
            sender = (m.get("sender") or "").strip()
            if any(sid in sender for sid in SELF_IDS):
                ts = m.get("timestamp", 0)
                if ts > my_last_ts:
                    my_last_ts = ts
        info["my_last_reply_ts"] = my_last_ts
        info["my_last_reply_time"] = datetime.fromtimestamp(my_last_ts).strftime("%Y-%m-%d %H:%M") if my_last_ts else "(无回复)"
        if my_last_ts < info["at_ts"]:
            info["hours_overdue"] = max(0, int((time.time() - info["at_ts"]) / 3600))
            info["overdue"] = True
            overdue.append(info)
        else:
            info["overdue"] = False
    overdue.sort(key=lambda x: x.get("hours_overdue", 0), reverse=True)

    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since, "window_days": args.days,
        "n_groups_with_at": len(by_chat),
        "n_overdue": len(overdue),
        "overdue": overdue[:30],
    }
    out = os.path.join(ROOT, "replies.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[replies] ✓ {len(overdue)} overdue (of {len(by_chat)} groups with @)", file=sys.stderr)
    print(f"[replies] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
