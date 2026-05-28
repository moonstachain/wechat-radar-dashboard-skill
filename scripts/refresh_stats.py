#!/usr/bin/env python3
"""refresh_stats.py — aggregate wx stats per group → write stats.json

  · per-group wx stats call ≈ 0.06s
  · ~60 groups ≈ 4 sec total
  · acceptable as periodic refresh, not blocking GET /api/data

Output → ROOT/stats.json, consumed by server.py fetch_real.
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


def run_wx(args, timeout=15):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import windows as _windows  # noqa

    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="YYYY-MM-DD start date (default: from config.windows.stats_days)")
    ap.add_argument("--days", type=int, default=_windows().get("stats_days", 30))
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    since = args.since or (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"[stats] fetching sessions (-n {args.limit}) …", file=sys.stderr)

    sess_resp = run_wx(["sessions", "-n", str(args.limit)])
    sessions = sess_resp.get("sessions", []) if isinstance(sess_resp, dict) else sess_resp
    groups = [s for s in sessions if s.get("chat_type") == "group"]
    print(f"[stats] aggregating {len(groups)} groups since {since}…", file=sys.stderr)

    t0 = time.time()
    per_group, failed = [], []
    total_msgs = 0
    type_tally, sender_tally = {}, {}
    # Stage 10: cross-group hourly distribution
    hour_tally = [0] * 24

    for i, g in enumerate(groups):
        chat_key = g.get("username") or g.get("chat") or ""
        chat_name = g.get("chat") or chat_key
        if not chat_key:
            continue
        try:
            s = run_wx(["stats", chat_key, "--since", since])
            n = int(s.get("total") or 0)
            total_msgs += n
            for bt in s.get("by_type", []):
                t = bt.get("type") or "?"
                type_tally[t] = type_tally.get(t, 0) + int(bt.get("count") or 0)
            # Stage 10: aggregate hourly
            for bh in s.get("by_hour", []):
                h = int(bh.get("hour", -1))
                if 0 <= h < 24:
                    hour_tally[h] += int(bh.get("count") or 0)
            for snd in (s.get("top_senders") or [])[:5]:
                name = (snd.get("sender") or "").strip()
                if not name:
                    continue
                rec = sender_tally.setdefault(name, {"n": 0, "groups": set()})
                rec["n"] += int(snd.get("count") or 0)
                rec["groups"].add(chat_name[:20])
            per_group.append({"chat": chat_name, "key": chat_key, "total": n})
        except Exception as e:
            failed.append({"chat": chat_name, "err": str(e)[:80]})
        if (i + 1) % 10 == 0 or i == len(groups) - 1:
            print(f"  {i+1}/{len(groups)} · {time.time()-t0:.1f}s", file=sys.stderr)

    elapsed = time.time() - t0
    n_ok = len(per_group)
    avg = round(total_msgs / max(n_ok, 1)) if n_ok else 0

    sources_ranked = sorted(
        ({"name": k, "n": v["n"], "where": ", ".join(sorted(v["groups"]))[:60],
          "extra": f"{len(v['groups'])} 群"}
         for k, v in sender_tally.items()),
        key=lambda x: x["n"], reverse=True,
    )[:8]
    per_group_sorted = sorted(per_group, key=lambda x: x["total"], reverse=True)

    # Stage 10: mute_candidates = high noise groups absent from focus/mentions
    focus_groups, mention_groups = set(), set()
    try:
        import json as _j
        llm_path = os.path.join(ROOT, "llm_output.json")
        if os.path.exists(llm_path):
            llm = _j.load(open(llm_path, encoding="utf-8"))
            focus_groups = {f.get("group", "")[:20] for f in (llm.get("focus", []) + llm.get("actions", []))}
        mention_path = os.path.join(ROOT, "mentions.json")
        if os.path.exists(mention_path):
            mt = _j.load(open(mention_path, encoding="utf-8"))
            mention_groups = {g.get("group", "")[:20] for g in mt.get("by_group", [])}
    except Exception:
        pass

    mute_candidates = []
    for g in per_group_sorted[:30]:
        gname = g["chat"][:20]
        if g["total"] < 200:
            continue
        if gname in focus_groups or gname in mention_groups:
            continue
        mute_candidates.append({
            "chat": g["chat"], "total": g["total"],
            "reason": "高消息量 + 0 focus + 0 @你",
            "signal_score": 0, "noise_score": g["total"],
        })

    payload = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since, "window_days": args.days,
        "n_groups": len(groups), "n_groups_ok": n_ok, "n_failed": len(failed),
        "elapsed_sec": round(elapsed, 2),
        "total_messages": total_msgs, "avg_per_group": avg,
        "by_type": sorted(({"type": t, "count": c} for t, c in type_tally.items()),
                          key=lambda x: x["count"], reverse=True),
        # Stage 10 new fields
        "by_hour_cross_group": [{"hour": h, "count": hour_tally[h]} for h in range(24)],
        "mute_candidates": mute_candidates[:10],
        "top_groups_by_msgs": per_group_sorted[:20],
        "top_senders_cross_group": sources_ranked,
        "failed": failed,
    }

    # Stage 10: append daily snapshot for state machine
    history_path = os.path.join(ROOT, "history.json")
    history = []
    if os.path.exists(history_path):
        try:
            history = json.load(open(history_path, encoding="utf-8"))
        except Exception:
            history = []
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot = {
        "date": today, "ts": int(time.time()),
        "n_groups": len(groups), "total_messages": total_msgs, "avg_per_group": avg,
        "n_failed": len(failed),
        "group_msg_counts": {g["chat"][:30]: g["total"] for g in per_group_sorted[:30]},
    }
    history = [h for h in history if h.get("date") != today] + [snapshot]
    history = history[-30:]
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    out_path = os.path.join(ROOT, "stats.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[stats] ✓ {elapsed:.1f}s · total={total_msgs:,} · avg={avg} · failed={len(failed)}",
          file=sys.stderr)
    print(f"[stats] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
