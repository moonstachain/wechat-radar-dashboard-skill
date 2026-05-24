# Architecture

## High-level

```
┌─────────────────────────────────────────────────┐
│ Browser  http://127.0.0.1:8786                  │
│   frontend/index.html (Tailwind + vanilla JS)   │
│   ├─ /api/config  → brand                       │
│   ├─ /api/data    → KPI + briefing + 3 cols     │
│   ├─ /api/all-groups, /api/favorites            │
│   ├─ /api/daemon-status (every 30s)             │
│   └─ /api/launchd-fire (全量同步 button)         │
└──────────────────┬──────────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────────┐
│ scripts/server.py   (Python stdlib, ~280 lines) │
│   · 60s cache keyed by (days,)                  │
│   · 5min cache for /api/all-groups, /favorites  │
│   · Triple-fallback merge:                      │
│       real-full   = all 4 cache JSONs present   │
│       real-kpi-only = no llm_output.json        │
│       mock        = wx-daemon down              │
│       inline      = server itself unreachable   │
└──────────────────┬──────────────────────────────┘
                   │ subprocess + read JSON
        ┌──────────┴───────────────────────────┐
        ▼                                       ▼
┌──────────────────┐                  ┌──────────────────────┐
│ wx (Rust binary) │                  │ 4 cache JSON files   │
│ jackwener/wx-cli │                  │ stats.json (3.6s)    │
│ ↓                │                  │ links.json (3.5s)    │
│ wx-daemon        │                  │ mentions.json (2.3s) │
│ ↓                │                  │ llm_output.json      │
│ ~/.wx-cli/cache  │                  │   (24s + ¥0.17)      │
│ ↓                │                  └──────────▲───────────┘
│ WeChat local DB  │                             │
│ (decrypted)      │                  ┌──────────┴───────────┐
└──────────────────┘                  │ 4 refresh scripts    │
                                      │ run via launchd      │
                                      │ 3×/day (07:30/12:30/ │
                                      │ 19:30)               │
                                      └──────────────────────┘
```

## Triple-fallback (server.py merge logic)

Every `/api/data` request:

1. Try `fetch_real(days)` →
   - Get `wx sessions -n 500` (always works if daemon up)
   - Get `wx unread --filter group` (always works)
   - **Merge in `mentions.json` if exists** → real `at_me` + multi-window
   - **Merge in `stats.json` if exists** → real `total_messages` + `sources`
   - **Merge in `links.json` if exists** → real `links_aggregated`
   - **Merge in `llm_output.json` if exists** → real `briefing` + `focus` + `actions`
     - If all 4 cache files: `_mode = "real-full"`
     - Else: `_mode = "real-kpi-only"`
2. If `wx` call throws (daemon down): fall back to `frontend/mock_data.json`
   - `_mode = "mock"`, `_error` populated
3. If server itself unreachable: frontend has `FALLBACK` inline copy of mock data → still renders

This means **UI never blanks**. Failure mode is degrading data, not blank pixels.

## Cache strategy

| Cache | TTL | Reason |
|---|---|---|
| `_cache[(days,)]` (main `/api/data`) | 60s | Frequent re-render; need responsiveness |
| `_aux_cache["all_groups"]` | 5min | Drawer-only, cheap to recompute |
| `_aux_cache["favorites"]` | 5min | Same |
| `aux_daemon_status()` | 0 (no cache) | Footer refreshes every 30s, want truth |

`?days=N` creates separate cache entries per window so switching `日 ↔ 月` doesn't cache-bust each other.

## Refresh script dependencies

```
refresh_stats.py    → stats.json    (no deps; wx stats × all groups)
refresh_links.py    → links.json    (no deps; wx history --type link × all groups)
refresh_mentions.py → mentions.json (reads config.at_queries + config.self_ids)
llm_classify.py     → llm_output.json (reads config.self_ids + config.llm.*)
```

Independent: can run in any order. `launch_refresh.py` runs them sequentially because LLM is slow + want to fail-fast on cheap ones.

## Why Python stdlib for server

- Zero pip dependencies (one less thing to break for the user)
- `http.server.HTTPServer` is enough for 1-user local dashboard
- Easier to audit
- Future: if scale needs Flask/FastAPI, swap `H` handler class

## Why launchd Python entrypoint (not bash)

The macOS TCC (Transparency, Consent, Control) system blocks `/bin/bash` from
accessing `~/Documents/` under launchd by default. Workaround required granting
`bash` Full Disk Access via System Settings — and even then it sometimes failed.

Python interpreter (`/opt/homebrew/bin/python3` or `/usr/bin/python3`) is more
reliably TCC-friendly when run via launchd. So `launch_refresh.py` is the
entrypoint, and it shells out to scripts via `subprocess.run([sys.executable, ...])`.

## Why `wx stats` >>> `wx history` for aggregation

Probed on 1 group (an active discussion group, n=2946 messages in 30d):
- `wx history <group> --since 30d -n 5000 --json` → 11.4 seconds
- `wx stats <group> --since 30d --json` → 0.06 seconds (200× faster)

`wx stats` returns `{total, by_type, top_senders, by_hour}` directly — exactly
what aggregation wants. Always prefer `stats` for counts; use `history` only when
you need actual message content (e.g., LLM input, link extraction).

## Why 4-window pre-compute for mentions

`wx search "@<nick>" --since N --json` is 0.9s per window. Computing 4 windows
(1d/3d/7d/30d) costs 3.6s total. Pre-computing all 4 means the dashboard segment
switcher (`日/周/月` button) can pick the right window from cache without
re-querying. Stats stays single-window (30d) because re-running it per window
would add real cost.
