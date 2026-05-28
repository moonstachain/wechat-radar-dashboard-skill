#!/usr/bin/env python3
"""refresh_private.py — Stage 12 子模块 M1.2 (私聊接入).

wx sessions filter chat_type=private → 1-on-1 私聊元数据 + 你回了没.
Reads SELF_IDS from config.json (no hardcoded wxid).

Output → ROOT/private.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDED_RE = re.compile(r'扑克|德州|poker|博彩|赌', re.IGNORECASE)


def wx(args, timeout=15):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import self_ids as _sids  # noqa

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    SELF_IDS = _sids()
    if not SELF_IDS:
        print("⚠ config.json self_ids 空 — 无法识别你自己的发言, 私聊方向会不准", file=sys.stderr)

    since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"[private] scanning 1-on-1 since {since}…", file=sys.stderr)

    t0 = time.time()
    sess = wx(["sessions", "-n", "500"]).get("sessions", [])
    privates = [s for s in sess if s.get("chat_type") == "private"]
    privates = [p for p in privates if not EXCLUDED_RE.search((p.get("chat") or "") + (p.get("summary") or ""))]
    print(f"[private] {len(privates)} private chats", file=sys.stderr)

    overdue, active = [], []
    for p in privates:
        chat = p.get("chat", "")
        username = p.get("username", "")
        try:
            h = wx(["history", username or chat, "--since", since, "-n", "50"]).get("messages", [])
        except Exception:
            h = []
        if not h:
            continue
        their_last = None
        my_last = None
        for m in h:
            sender = (m.get("sender") or "").strip()
            ts = m.get("timestamp", 0)
            is_self = any(sid in sender for sid in SELF_IDS) or sender == "" or sender == chat
            if is_self:
                if not my_last or ts > my_last["timestamp"]: my_last = m
            else:
                if not their_last or ts > their_last["timestamp"]: their_last = m

        info = {
            "chat": chat, "username": username,
            "unread": int(p.get("unread") or 0),
            "last_summary": (p.get("summary") or "")[:80],
            "last_time": p.get("time", ""), "last_timestamp": p.get("timestamp", 0),
        }
        if their_last and (not my_last or their_last["timestamp"] > my_last["timestamp"]):
            info["overdue"] = True
            info["their_last_content"] = (their_last.get("content") or "")[:120]
            info["their_last_time"] = their_last.get("time", "")
            info["hours_overdue"] = max(0, int((time.time() - their_last["timestamp"]) / 3600))
            overdue.append(info)
        else:
            info["overdue"] = False
            active.append(info)

    overdue.sort(key=lambda x: x.get("hours_overdue", 0), reverse=True)
    active.sort(key=lambda x: x.get("last_timestamp", 0), reverse=True)

    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since, "window_days": args.days,
        "n_private_total": len(privates),
        "n_overdue": len(overdue),
        "n_with_msgs_in_window": len(overdue) + len(active),
        "elapsed_sec": round(time.time() - t0, 2),
        "overdue_to_me": overdue[:20],
        "active_recent": active[:20],
    }
    out = os.path.join(ROOT, "private.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[private] ✓ {payload['elapsed_sec']}s · {len(privates)} 私聊 · {len(overdue)} 欠回",
          file=sys.stderr)
    print(f"[private] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
