# wechat-radar-dashboard

> 本地优先 · 不上云 · LLM 智能列 · 微信群聊情报驾驶舱
>
> 把 N 个微信群的"我每天应该看什么"压缩成一张看板. 数据全在本机, 只有按你配置的 prompt 调一次 LLM 出 briefing/focus/actions 三列.

A **Claude Code skill** that builds a personal-use, local-only intelligence dashboard for WeChat group chats. Distilled from a 13-stage n=1 deployment (PII-stripped).

## What it gives you

- **4 KPI cards** with real values: 活跃群 / 总消息 / @ 我的 / 静默群 — all window-switchable (日/周/月/季/年)
- **3 智能列**: 最值得关注 / 可行动项 / 情报源 — LLM 排序的高信号
- **4 tab 视图**: Brief (主看板) / Live (时间流) / Cross (跨群发言者 + 类型分布) / Link (URL 真相镜子)
- **6 类 drawer**: @ mentions 详情 / 所有群 / 收藏 / 未分组 / wx-daemon 状态 / 设置
- **launchd 3×/day 自刷**, 重扫按钮 + 全量同步按钮真区分
- **三重 fallback**: real-full → real-kpi-only → mock → inline (UI 永不空白)

## Quick start (5 commands after wx-cli init)

```bash
# 1. clone
git clone https://github.com/moonstachain/wechat-radar-dashboard-skill.git ~/Documents/wechat-radar-dashboard
cd ~/Documents/wechat-radar-dashboard

# 2. config (copy template + fill in YOUR self IDs)
cp config.example.json config.json
# Edit config.json: set self_ids = ["YourNick"], at_queries = ["@YourNick"], brand, LLM provider

# 3. first refresh (assumes wx-cli already `sudo wx init`-ed)
python3 scripts/refresh_stats.py
python3 scripts/refresh_mentions.py
python3 scripts/refresh_links.py
python3 scripts/llm_classify.py     # needs DASHSCOPE_API_KEY in env, ~¥0.17

# 4. start server (port 8786)
python3 scripts/server.py

# 5. open
open http://localhost:8786
```

## Prerequisites (before step 1)

1. macOS + WeChat 4.x logged in
2. `npm install -g @jackwener/wx-cli`
3. **One-time `sudo wx init`** (memory scan for DB keys) — see [references/install-guide.md](references/install-guide.md) for the codesign sub-component traps you WILL hit
4. (Optional) DashScope / Claude / OpenAI API key for the LLM intelligence layer

## Cost & privacy contract

| Layer | Cost | Where data goes |
|---|---|---|
| wx stats / links / mentions | 0 ¥ | Pure local subprocess to wx-cli (Rust binary, reads decrypted SQLite locally) |
| LLM classify (24h text msgs) | ~¥0.17/run × 3 runs/day = ¥0.51/day | Filtered text (no XML / no media / no SELF msgs) sent to chosen LLM provider |
| Server | 0 | Listens on 127.0.0.1 only, no public exposure |
| GitHub mirror | 0 | Code only (mock + scripts), all `*.json` data files are `.gitignore`-d |

Total: **~¥15/month + 0 chat-content leak risk**

## What you skip (intentionally NOT in scope)

- ❌ Sending WeChat messages (this is read-only)
- ❌ Cross-platform IM (WeChat only via wx-cli)
- ❌ SaaS deployment (intentionally local; can't run on a server because needs WeChat.app + sudo)
- ❌ Auto-action execution (LLM identifies things to do; you read + act manually)

## Customize

Edit `config.json` (created from template):

```json
{
  "brand": "MY RADAR",
  "self_ids": ["YourNick", "your_wxid"],
  "at_queries": ["@YourNick"],
  "llm": {"provider": "dashscope", "model": "qwen-plus", "api_key_env": "DASHSCOPE_API_KEY"},
  "windows": {"stats_days": 30, "links_days": 30, "mentions_days": 7, "llm_hours": 24}
}
```

For deeper customization (LLM prompt template, collection grouping, launchd timing): see [references/](references/).

## Architecture (one-line)

```
WeChat DB → wx-cli (Rust) → 4 refresh scripts → 4 cache JSON → server.py merge → /api/data → SPA frontend
                                                                    ↑
                                                          config.json (你的 self IDs / brand / LLM)
```

Full diagram + data flow → [references/architecture.md](references/architecture.md)

## Distilled from

A 13-stage personal deployment (2026-05-24) — see [examples/n1-deployment.md](examples/n1-deployment.md) for the walkthrough including all 7 distortion surprises that the n=1 hit but the skill now avoids.

## License

MIT. Upstream [jackwener/wx-cli](https://github.com/jackwener/wx-cli) is Apache-2.0 (separate project, not bundled here).
