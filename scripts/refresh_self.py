#!/usr/bin/env python3
"""refresh_self.py — Stage 12 子模块 M5.2 (自我角色镜子).

跨群分析你 (SELF_IDS) 的角色:
  · 在哪些群是 top sender (你是中心)
  · 在哪些群完全没说话 (你是潜水)
  · 跨群总发言 N 条 / 占总消息 X%
  · my_by_hour: 你最活跃的小时分布

Reads SELF_IDS from config.json.
Output → ROOT/self.json
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
    from _config import self_ids as _sids, windows as _windows  # noqa

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=_windows().get("stats_days", 30))
    args = ap.parse_args()

    SELF_IDS = _sids()
    if not SELF_IDS:
        print("❌ config.json self_ids 空 — 无法识别你, refresh_self 退出", file=sys.stderr)
        sys.exit(1)

    since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"[self] scanning self role since {since}…", file=sys.stderr)

    t0 = time.time()
    sess = wx(["sessions", "-n", "500"]).get("sessions", [])
    groups = [s for s in sess if s.get("chat_type") == "group"]
    groups = [g for g in groups if not EXCLUDED_RE.search(g.get("chat", ""))]
    print(f"[self] scanning {len(groups)} groups…", file=sys.stderr)

    my_active, my_silent, my_normal = [], [], []
    my_total_msgs = 0
    my_by_hour = [0] * 24
    other_total_msgs = 0

    for i, g in enumerate(groups):
        chat_key = g.get("username") or g.get("chat", "")
        chat_name = g.get("chat", "") or chat_key
        if not chat_key:
            continue
        try:
            s = wx(["stats", chat_key, "--since", since])
        except Exception:
            continue
        total = int(s.get("total") or 0)
        if total == 0:
            continue
        other_total_msgs += total
        top_senders = s.get("top_senders") or []
        my_n = 0
        for snd in top_senders:
            sender = (snd.get("sender") or "").strip()
            if any(sid in sender for sid in SELF_IDS):
                my_n += int(snd.get("count") or 0)
        my_total_msgs += my_n
        my_pct = (my_n / total * 100) if total else 0
        my_rank = next((idx+1 for idx, snd in enumerate(top_senders)
                        if any(sid in (snd.get("sender") or "") for sid in SELF_IDS)), None)
        info = {"chat": chat_name, "total": total, "my_n": my_n,
                "my_pct": round(my_pct, 1), "my_rank": my_rank}
        if my_n == 0:
            my_silent.append(info)
        elif my_rank and my_rank <= 5 and my_n >= 5:
            my_active.append(info)
        else:
            my_normal.append(info)

        if my_n > 0:
            for bh in s.get("by_hour", []):
                h = int(bh.get("hour", -1))
                if 0 <= h < 24:
                    my_by_hour[h] += int((bh.get("count") or 0) * my_pct / 100)

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(groups)} · {time.time()-t0:.1f}s", file=sys.stderr)

    my_active.sort(key=lambda x: x["my_n"], reverse=True)
    my_silent.sort(key=lambda x: x["total"], reverse=True)
    my_normal.sort(key=lambda x: x["my_n"], reverse=True)

    elapsed = time.time() - t0
    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since, "window_days": args.days,
        "n_groups_scanned": len(groups),
        "elapsed_sec": round(elapsed, 2),
        "my_total_msgs": my_total_msgs,
        "other_total_msgs": other_total_msgs - my_total_msgs,
        "my_pct_of_all": round(my_total_msgs / other_total_msgs * 100, 2) if other_total_msgs else 0,
        "n_active": len(my_active), "n_silent": len(my_silent), "n_normal": len(my_normal),
        "active_groups": my_active[:15],
        "silent_groups": my_silent[:15],
        "my_by_hour": [{"hour": h, "count": my_by_hour[h]} for h in range(24)],
    }
    out = os.path.join(ROOT, "self.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[self] ✓ {elapsed:.1f}s · 我发 {my_total_msgs} 条 ({payload['my_pct_of_all']}%) · "
          f"中心 {len(my_active)} 群 · 潜水 {len(my_silent)} 群", file=sys.stderr)
    print(f"[self] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
