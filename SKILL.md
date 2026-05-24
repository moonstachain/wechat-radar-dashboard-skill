---
name: wechat-radar-dashboard
description: Build a local-only WeChat group chat intelligence dashboard on macOS. Wraps wx-cli (jackwener/wx-cli Rust binary) as the data layer + LLM-classified focus/actions/briefing + 4-tab views (Brief / Live / Cross / Link) + launchd auto-refresh. Triple-fallback architecture (real-full → real-kpi-only → mock → inline) so it never blanks. Use when user wants to monitor many WeChat groups, extract daily signals, surface @ mentions and shared URLs, all without exposing chat content to cloud. Triggers on phrases like "微信群聊看板 / wechat dashboard / 群情报 / wx-cli dashboard / 复刻 QIAOMU RADAR / 微信群聊 LLM 摘要 / 群聊驾驶舱".
---

# wechat-radar-dashboard

> **What this is**: a Claude Code skill that builds a personal-use, local-only intelligence dashboard for WeChat group chats. Distilled from a 13-stage n=1 deployment (PII-stripped).

## When to invoke

User wants any of:
- "复刻 / 做一个微信群聊情报看板"
- "把我 N 个群的消息聚合 + LLM 出摘要 + 找出 @ 我的"
- "wx-cli 出 dashboard"
- "群聊驾驶舱 / QIAOMU RADAR 同款"
- "本地微信 LLM 摘要 不上云"
- "看 N 个群里每天值得回复的事"

Skip when:
- User wants WeChat *bot/automation* (this is read-only intelligence)
- User wants cross-platform IM (this is WeChat-only via wx-cli)
- User wants to ship WeChat data to a SaaS dashboard (this is intentionally local)

## What you build for the user

A 4-stack pipeline that runs on their Mac:

1. **wx-cli (Rust binary, upstream `jackwener/wx-cli`)** — already-installed local data CLI that reads decrypted WeChat databases
2. **4 refresh scripts** — `refresh_stats.py` (3.6s, 0 cost), `refresh_links.py` (3.5s, 0 cost), `refresh_mentions.py` (2.3s, 0 cost), `llm_classify.py` (24s + ~¥0.17 via DashScope qwen-plus or Claude/OpenAI)
3. **Python stdlib HTTP server (`server.py`)** with 5 endpoints + triple-fallback merge logic + 60s cache
4. **Single-file SPA (`index.html`)** with Tailwind CDN, 4-tab view (Brief / Live / Cross / Link), 6 drawer types, hover tooltips, segment-driven window filtering

Plus a **launchd plist template** so the 4 scripts auto-fire 3×/day.

## Hard prerequisites (must confirm with user before starting)

1. macOS (Apple Silicon or Intel) + WeChat desktop 4.x logged in
2. Node ≥ 14 (for `npm install -g @jackwener/wx-cli`) or `curl` (for shell install)
3. **Comfort with `sudo wx init`** — one-time root-level memory scan to extract WeChat database keys. **No alternative path exists.** Block on this consent before proceeding.
4. Optional LLM API key (DashScope / Claude / OpenAI). Without it the intelligence layer falls back to mock.

## Build flow (10 steps, ~1 hour wall clock)

1. **Confirm prerequisites** — block on `sudo wx init` consent
2. **Verify wx-cli** — `which wx`, if missing → install via `npm install -g @jackwener/wx-cli`
3. **One-time init** — guide user through `codesign --force --deep --sign - /Applications/WeChat.app` + `sudo wx init` (see [references/install-guide.md](references/install-guide.md) for codesign sub-component traps)
4. **Drop scripts** — copy `scripts/*.py` + `frontend/*` to user's target dir (e.g. `~/Documents/wechat-radar-dashboard/`)
5. **Configure** — copy `config.example.json` → `config.json`, fill in user's WeChat display names + LLM provider
6. **First refresh** — `python3 refresh_stats.py && python3 refresh_links.py && python3 refresh_mentions.py && python3 llm_classify.py` to populate caches
7. **Start server** — `python3 server.py` (port 8786)
8. **Verify in browser** — open http://localhost:8786, confirm "wx-cli + qwen · live" lime badge
9. **Optional launchd** — `cp scripts/com.example.wxradar.refresh.plist ~/Library/LaunchAgents/`, edit user paths, `launchctl bootstrap`
10. **Evolution Note** — record what surprises came up (the n=1 had 7 surprises documented in [references/distortion-pitfalls.md](references/distortion-pitfalls.md))

## Customization points (config.json)

```json
{
  "brand": "MY RADAR",                  // sidebar brand text
  "self_ids": ["YourNickname", "your_wxid"],  // filter own messages from sources/mentions
  "at_queries": ["@YourNickname"],      // wx search keywords for @-counting
  "llm": {
    "provider": "dashscope",            // dashscope | openai | claude
    "model": "qwen-plus",
    "api_key_env": "DASHSCOPE_API_KEY"
  },
  "windows": {
    "stats_days": 30,
    "links_days": 30,
    "mentions_days": 7,
    "llm_hours": 24
  }
}
```

Scripts read `config.json` at startup; `server.py` exposes `/api/config` so frontend renders the brand.

## Architecture decisions worth knowing before iterating

- **Triple-fallback**: server tries `real-full` → falls back to `real-kpi-only` (if LLM cache missing) → `mock` (if wx-daemon down) → `inline` (if server itself unreachable). UI never blanks.
- **`wx stats` >>> `wx history` for aggregation**: 0.06s vs 11s per group (200× faster). Always prefer stats.
- **Multi-window pre-compute**: `refresh_mentions.py` computes 4 windows (1d/3d/7d/30d) in one pass since each call is 0.9s. Stats stays single-window.
- **launchd Python entrypoint, not bash**: avoids macOS TCC Full Disk Access trap on `~/Documents/` paths.
- **PII isolation**: ALL data JSONs (`stats.json`, `links.json`, `mentions.json`, `llm_output.json`) are in `.gitignore`. Only code + mock + config-template ships to repo.

See [references/architecture.md](references/architecture.md) for the full diagram.

## Hard pitfalls (top 7 — read [references/distortion-pitfalls.md](references/distortion-pitfalls.md) for all 13)

1. **`zsh` 中文注释陷阱**: copy-pasting commands with `# 中文` tail breaks (zsh treats `#` as literal unless `setopt interactive_comments`)
2. **codesign sub-component permission**: `ConfSDKdyn.framework` blocks `--deep --sign` until you `sudo codesign --remove-signature` it first
3. **`~/.wx-cli/daemon.pid` is JSON not int**: don't `int()` it raw
4. **`wx daemon status` has no `--json`**: must parse text
5. **`navigator.clipboard.writeText` denied in non-user-gesture / sandbox**: wrap in try/catch + toast the error
6. **mock data must be honest about scale**: original mock had 183k messages, real was 33k (5.5× inflation hurt trust)
7. **Decorative buttons silently break trust**: every interactive element must be REAL or explicitly disabled/⏳-marked

## What you do NOT do

- Do NOT write/send WeChat messages (read-only intelligence only)
- Do NOT ship chat content to any cloud (LLM call is opt-in + sends only filtered text, never raw DB)
- Do NOT auto-execute the actions the LLM identifies (user reads + acts manually)
- Do NOT skip the 50-button reality check ([references/50-button-audit.md](references/50-button-audit.md)) — every button must be REAL or explicitly disabled

## Output to user after build

A summary with:
- URL: http://localhost:8786
- Initial mode (`real-full` if all 4 caches populated)
- Cost ledger (`¥X.XX/day` based on LLM provider × 3 daily fires)
- Backlog items (5-7 known unimplemented features, explicitly listed so user doesn't expect them)
- Next-iter suggestions (custom collections.json / launchd timing tune / etc.)

## Provenance

Distilled 2026-05-24 from a 13-stage personal deployment. PII removed:
- self IDs → config-driven (no example real wxids)
- group names in mock → fictional ("AI Builders Hub", "Work Sync Channel", etc.)
- LLM prompt "RAY 视角" → generic "{{USER_NICK}} 视角"
- brand "QIAOMU RADAR / YUANLI RADAR" → user's choice via config

Skill is **MIT licensed**. The upstream wx-cli is Apache-2.0 (separate project, not bundled).

## References

- [references/architecture.md](references/architecture.md) — triple-fallback diagram + data flow
- [references/install-guide.md](references/install-guide.md) — wx init + codesign traps + 3-line cheatsheet
- [references/llm-prompt-template.md](references/llm-prompt-template.md) — the qwen-plus prompt + customization
- [references/distortion-pitfalls.md](references/distortion-pitfalls.md) — 13 traps the n=1 hit
- [references/50-button-audit.md](references/50-button-audit.md) — the audit framework (apply to your build)
- [examples/n1-deployment.md](examples/n1-deployment.md) — sanitized walkthrough of the original n=1
