# LLM Prompt Template

## What it does

`scripts/llm_classify.py` collects the last N hours (default 24) of **text** messages
from all your groups, filters out your own messages (via `config.self_ids`), and
asks the LLM for a single JSON response with three sections:

- `briefing`: 60-120 char摘要 in your first-person voice ("RAY 今天群里最值得关注的几件事")
- `focus`: 5-8 high-signal items with title/group/time/tags
- `actions`: 3-5 things requiring immediate response (报名/团购/回答/抓机会)

## Default prompt (中文)

```
你是 {user_nick} 的微信群聊情报分析助手. 返回严格 JSON 对象, 不要 markdown 代码块、不要解释.

下面是过去 24 小时 {user_nick} 接收到的 N 条群文本消息:

[群名] HH:MM 发言者: 消息内容
[群名] HH:MM 发言者: 消息内容
...

请分析后返回 JSON, 结构:

{
  "briefing": "60-120 字今日重点摘要, 必须站在 {user_nick} 第一视角讲'今天群里最值得关注的几件事', 不要套话",
  "focus": [
    {"title":"原文 35 字以内","group":"群名","time":"HH:MM","tags":["工具/产品" 或 "链接信号" 或 "可跟进" 或 "机会/需求"],"count":1}
  ],
  "actions": [
    {"cat":"看报名/活动" 或 "看采购/团购" 或 "可回复推荐" 或 "机会/需求","catColor":"amber","time":"HH:MM","title":"原文 50 字以内","group":"群名"}
  ]
}

要求:
- focus 5-8 条, 选 {user_nick} 真正应该关注的 (不是闲聊/打招呼/红包/广告/营销机器人)
- actions 3-5 条, 必须可立即响应 (报名/团购/回答问题/抓机会)
- 跳过纯营销/推销机器人主导的群
- 去重 (同一事件不要出两条 focus)
- tags 数组每条 1-3 个
- 不要包含 {user_nick} 自己的发言
```

## Customization recipes

### Recipe A: Different role / focus area

Edit `scripts/llm_classify.py` `SYSTEM` and `build_user_prompt`:

```python
# Original:
SYSTEM = "你是 {user_label} 的微信群聊情报分析助手..."

# For an investor:
SYSTEM = "你是 {user_label} 的投资群情报分析助手, 重点关注: \
  一级市场融资 / 二级市场异动 / 行业政策 / 投资人观点 / 项目方动态."

# For a content creator:
SYSTEM = "你是 {user_label} 的内容选题情报分析助手, 重点关注: \
  热点话题 / 爆款拆解 / 流量趋势 / 平台规则变化 / 同行内容."
```

### Recipe B: English output

If your groups are primarily English-speaking, replace `SYSTEM` and the JSON
structure prompt with English versions. The model will follow whatever language
the prompt is in.

### Recipe C: More aggressive spam filter

In `requirements:` section of `build_user_prompt`, add explicit group name patterns:

```python
- 跳过下列群: *好物分享* / *社群创富* / *扑克* / *福利分享* / *团购* / *推广*
```

Or maintain `config.spam_groups_hint` and inject it.

### Recipe D: Cost reduction

Currently feeds **all 24h text msgs** (len>5) to the LLM. ~30K tokens. ¥0.17/run.

To cut cost:
- Reduce `windows.llm_hours` to 12 → ~half tokens → ~¥0.08/run
- Pre-filter via `wx unread` only (skip read msgs you already saw) — needs new logic
- Sample (e.g., 50% random subset of msgs) — simpler but lossy

### Recipe E: Different LLM provider

Edit `config.json`:

```json
{
  "llm": {
    "provider": "claude",                        // dashscope | openai | claude | deepseek | moonshot
    "model": "claude-sonnet-4-7",
    "api_key_env": "ANTHROPIC_API_KEY",
    "endpoint": "https://api.anthropic.com/v1/messages"
  }
}
```

`llm_classify.py` auto-handles the API schema difference (Claude vs OpenAI-compatible).
For Claude: uses `messages` array with `system` field. For others: OpenAI-style
`response_format: {type:"json_object"}`.

⚠ Claude may need a few retries on JSON parsing since it doesn't have native
JSON response_format. The script regex-extracts the first `{...}` block as a
fallback.

### Recipe F: Different windows (`focus` from 6h, `briefing` from 24h)

Currently one prompt for both. To split:
- Copy `llm_classify.py` → `llm_classify_focus.py`, `--hours 6`, only return `focus`
- Copy → `llm_classify_briefing.py`, `--hours 24`, only return `briefing`
- Two `llm_output.json` files, server merges both

This doubles LLM cost but gives 6h-fresh focus + 24h briefing context.

## Output quality benchmarks (from n=1)

On 327 messages / 31K tokens (24h window):
- **Briefing quality**: 9/10 — captures real events (real-world n=1 caught 监管事件 / AI 发布 / 学习活动)
- **Focus dedup**: 6/10 — same event sometimes appears in 2 focus entries; add explicit `去重` rule
- **Actions precision**: 8/10 — most are real action items; occasional false positive (e.g., generic 推荐)
- **Spam filtering**: 9/10 —营销机器人主导的群基本被跳过, occasional bleed-through

If your groups have very different content style (e.g., enterprise vs personal),
expect to iterate the prompt 2-3 times to tune.

## Anti-patterns to avoid

1. **Don't ask for too many fields** — 8 focus + 5 actions + 1 briefing is sweet spot. Asking for 20 each → quality drops + token cost up.
2. **Don't include msg IDs / timestamps as raw numbers** — they don't help LLM and bloat prompt. Use `HH:MM` short format.
3. **Don't feed media/image messages** — only `type == "文本"` provides language signal. Other types are noise.
4. **Don't ask LLM to "summarize my groups"** — too generic. The "RAY 视角" first-person framing forces it to be selective.
5. **Don't bake your name into `SYSTEM` directly** — use `{user_label}` template so other users can copy the skill.
