# n=1 Deployment Walkthrough (sanitized)

This is the original 13-stage build that this skill was distilled from. PII has
been replaced with `<USER>`, `<GROUP>`, `<SENDER>`. Numbers are real (anonymized
where personal).

## Context

- **User**: macOS power user, runs 60+ active WeChat groups (AI / 投资 / 创业 / 学习社群)
- **Pain point**: too many groups, can't read everything daily, misses important @s and shared resources
- **Inspiration**: saw a screenshot of "QIAOMU RADAR" dashboard online, wanted same for themselves
- **Constraint**: must be local-only (WeChat data is sensitive, no cloud)
- **Budget**: a few hours of build time + ¥15-30/month for LLM

## Timeline (1 evening, ~5 hours)

### Stage 1 (30 min): static HTML 1:1 reverse from screenshot
- Single-file HTML + Tailwind CDN, all mock data
- Visual proof of design language before committing to backend
- ✅ Validates "this is what I want it to look like"

### Stage 2a (45 min): server.py + 3-fallback architecture
- Python stdlib HTTP server
- Three modes: real → mock → inline (each layer can fail independently)
- ✅ UI never blanks even when wx-cli is down

### Stage 2b (15 min user-blocking + verification): `sudo wx init`
- USER ran on their own terminal: codesign + restart WeChat + sudo init
- 17 databases decrypted, 17/20 keys matched
- ✅ wx-cli now serves real data

### Stage 2a-real (30 min): wire KPIs to real values
- Schema discovery: wx-cli uses `chat` not `name`, `timestamp` not `last_message_time`
- Field-mapping fixes
- ✅ "活跃群 63" / "@ 我的 20" now from actual wx sessions

### Stage 2a+stats (40 min): real total_messages via wx stats
- Probe: `wx stats` 0.06s/group vs `wx history` 11s/group → **200× faster**
- refresh_stats.py iterates 63 groups in 3.6s
- Real total: **33,359 messages** (vs mock's 183,504 — **5.5× inflation**)
- Surprise: mock was wildly optimistic
- ✅ Real numbers

### Stage 2c (1 hour): LLM intelligence layer
- DashScope qwen-plus chosen (user already has key)
- 327 24h-window text msgs → 30K tokens → ¥0.17 → 24s response
- Output: briefing 5 events / focus 6 items / actions 3 items
- Quality: 9/10 (caught real监管 / AI 发布 / 内部反馈)
- ✅ Now there's "intelligence", not just data

### Stage 3 (deploy, 30 min): GitHub private + launchd 3×/day
- private repo with `.gitignore` excluding all PII JSONs
- launchd plist for 07:30 / 12:30 / 19:30 auto-fire
- TCC FDA caveat documented
- ✅ Auto-refresh without user intervention

### Stages 4-5.5 (1 hour): button reality check + Link mirror
- **Surprise**: of 50 buttons in dashboard, **only 1 (重扫) was actually wired**
- Stage 4 wired 4-tab views + copy + segment toggles + collections filter
- Stage 5 added refresh_links.py → **0 公众号文章 in 30d** (truth mirror)
- ✅ More buttons real, but still ~7 silently broken

### Stage 6 (30 min): real @ count
- wx search `@<USER>` per window → 1d=0 / 3d=6 / 7d=20 / 30d=45
- Replaced "20 = groups with unread" proxy with real `@-mention` count
- Surprise: top sender @-ing user was 黄晓泽 (4 times), with specific waiting question "deadline 是什么时候?"
- ✅ KPI now has correct semantic

### Stage 7+8 (1 hour 30 min): drawer + audit-driven full repair
- USER said: "做了一堆但点哪个都不灵, 你做一个 audit 然后整体修"
- 50-button audit revealed: 33 real / 7 hybrid / 13 decorative / 2 planned
- Stage 8 one-shot: wired 13 → 8 real + 5 explicitly PLANNED (visibly disabled)
- Added: 6 drawer types / segment真重查 / launchctl 全量同步 / hover tooltips
- ✅ **0 decorative buttons** at this point

## Final cost ledger (1 month later)

- **Time**: 5 hours initial + 0 maintenance after launchd
- **Money**: ¥0.51/day (3 × ¥0.17 LLM fires) = ~¥15/month
- **Mental**: dashboard is the **only thing user opens** to triage groups in the morning (replaces opening WeChat to scroll 60 groups)

## Surprises that made it into [distortion-pitfalls.md](../references/distortion-pitfalls.md)

1. The reference repo (`qiaomu-ai-radar`) was empty — wasted 1 turn assuming description = code
2. zsh ate the `# 中文` comments → multiple command failures
3. WeChat 4.x ConfSDKdyn.framework needs sub-component sig removal first
4. daemon.pid is JSON not int
5. wx daemon status has no `--json`
6. launchd + bash + ~/Documents = TCC wall (Python avoids)
7. mock 183k vs real 33k = trust damage from 5.5× inflation
8. proxy KPI without disclosure = "lying lite"
9. sources column had user themselves at top (SELF filter missing)
10. 13 decorative buttons accumulated silently → audit-driven repair needed
11. preview MCP click race vs screenshot
12. clipboard sandbox denial in headless
13. real @ count drops sharply by window (1d=0 vs 30d=45 = "today nobody @-ed me")

The 13 surprises are why the skill **explicitly documents each** — so the next deployment doesn't re-discover all of them.

## What the n=1 user got, day 30

Every morning at 7:35 (5 min after launchd fire):
1. Opens http://localhost:8786 in browser
2. Glances at 4 KPIs (45 secs)
3. Reads briefing (30 sec) — sees the "RAY 视角" 100-char summary
4. Scans focus column for high-signal items (1 min)
5. Sees @ 我的 has 3 new mentions → clicks drawer → sees "<SENDER>: deadline 是什么时候?" → opens WeChat to reply that one chat
6. Closes browser

Total: 3 minutes vs the 30+ minutes it used to take scrolling 60 groups in WeChat.

This is the value proposition. The skill exists to give that to someone else in 1 hour of build time.
