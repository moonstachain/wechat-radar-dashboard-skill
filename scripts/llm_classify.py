#!/usr/bin/env python3
"""llm_classify.py — Pull last N hours of text msgs, ask LLM for briefing/focus/actions.

Supports multiple LLM providers (DashScope / OpenAI / Claude / DeepSeek / Moonshot) via config.json.
Filters out user's own messages via self_ids.

Cost (DashScope qwen-plus, 24h ~300 msgs ~30K tokens): ~¥0.17 per run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wx(args, timeout=15):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout)


def fetch_recent_msgs(self_ids: tuple, hours: int = 24, limit_per_group: int = 200):
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    sessions = wx(["sessions", "-n", "500"]).get("sessions", []) or []
    groups = [s for s in sessions if s.get("chat_type") == "group"]
    out = []
    for g in groups:
        key = g.get("username") or g.get("chat")
        name = g.get("chat") or key
        if not key:
            continue
        try:
            h = wx(["history", key, "--since", since, "-n", str(limit_per_group)])
            for m in (h.get("messages") or []):
                if m.get("type") != "文本":
                    continue
                content = (m.get("content") or "").strip()
                if len(content) < 8:
                    continue
                sender = (m.get("sender") or "").strip()
                if any(sid in sender for sid in self_ids):
                    continue
                out.append({"group": name[:24], "time": (m.get("time") or "")[-5:],
                            "sender": sender[:14] if sender else "?",
                            "content": content[:300]})
        except Exception:
            continue
    return out


def build_user_prompt(msgs, user_nick: str, brand: str):
    lines = [f"[{m['group']}] {m['time']} {m['sender']}: {m['content']}" for m in msgs]
    body = "\n".join(lines)
    user_label = user_nick or "the user"
    return f"""下面是过去 24 小时 {user_label} 接收到的 {len(msgs)} 条群文本消息:

{body}

请分析后返回 JSON, 结构:

{{
  "briefing": "60-120 字今日重点摘要, 必须站在 {user_label} 第一视角讲'今天群里最值得关注的几件事', 不要套话",
  "focus": [
    {{"title":"原文 35 字以内","group":"群名","time":"HH:MM","tags":["工具/产品" 或 "链接信号" 或 "可跟进" 或 "机会/需求"],"count":1}}
  ],
  "actions": [
    {{"cat":"看报名/活动" 或 "看采购/团购" 或 "可回复推荐" 或 "机会/需求","catColor":"amber","time":"HH:MM","title":"原文 50 字以内","group":"群名"}}
  ]
}}

要求:
- focus 5-8 条, 选 {user_label} 真正应该关注的 (不是闲聊/打招呼/红包/广告/营销机器人)
- actions 3-5 条, 必须可立即响应 (报名/团购/回答问题/抓机会)
- 跳过纯营销/推销机器人主导的群
- 去重 (同一事件不要出两条 focus)
- tags 数组每条 1-3 个
- 不要包含 {user_label} 自己的发言"""


SYSTEM = "你是 {user_label} 的微信群聊情报分析助手. 返回严格 JSON 对象, 不要 markdown 代码块、不要解释."


def call_llm(api_key, msgs, user_nick: str, brand: str, provider: str, model: str, endpoint: str, temperature: float):
    user_label = user_nick or "the user"
    sys_prompt = SYSTEM.format(user_label=user_label)
    user_prompt = build_user_prompt(msgs, user_nick, brand)

    if provider == "claude":
        # Anthropic API: different schema
        body = {
            "model": model,
            "max_tokens": 2048,
            "system": sys_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    else:
        # OpenAI-compatible (dashscope / openai / deepseek / moonshot)
        body = {
            "model": model,
            "messages": [{"role": "system", "content": sys_prompt},
                         {"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    req = urllib.request.Request(endpoint, method="POST", headers=headers,
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"))
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:400]}")

    if provider == "claude":
        content = data["content"][0]["text"]
        usage = data.get("usage", {})
    else:
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            raise RuntimeError(f"LLM returned non-JSON: {content[:200]}")
        parsed = json.loads(m.group(0))
    return parsed, usage


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import (self_ids as _sids, llm_provider, llm_model, llm_api_key,
                         llm_endpoint, llm_temperature, windows as _windows, brand as _brand)  # noqa

    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=_windows().get("llm_hours", 24))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    SELF_IDS = _sids()
    api_key = llm_api_key()
    if not api_key:
        print(f"❌ LLM API key not found (config.llm.api_key_env={(json.dumps(_sids()))}, env or ~/.zshrc)", file=sys.stderr)
        sys.exit(1)
    user_nick = SELF_IDS[0] if SELF_IDS else "user"
    b = _brand()

    print(f"[llm] provider={llm_provider()} · model={llm_model()} · user_nick={user_nick}", file=sys.stderr)
    print(f"[llm] fetching last {args.hours}h text messages…", file=sys.stderr)
    t0 = time.time()
    msgs = fetch_recent_msgs(SELF_IDS, hours=args.hours)
    total_chars = sum(len(m["content"]) for m in msgs)
    print(f"[llm] {len(msgs)} msgs · {total_chars:,} chars · ~{int(total_chars*0.7):,} tokens "
          f"· fetch {time.time()-t0:.1f}s", file=sys.stderr)
    if not msgs:
        print("[llm] no messages, exit", file=sys.stderr); sys.exit(0)
    if args.dry_run:
        print(build_user_prompt(msgs, user_nick, b["brand"])[:1200]); return

    print(f"[llm] calling {llm_model()}…", file=sys.stderr)
    t1 = time.time()
    try:
        result, usage = call_llm(api_key, msgs, user_nick, b["brand"],
                                 llm_provider(), llm_model(), llm_endpoint(), llm_temperature())
    except Exception as e:
        print(f"❌ LLM call failed: {e}", file=sys.stderr); sys.exit(2)
    llm_dt = time.time() - t1
    print(f"[llm] returned in {llm_dt:.1f}s · usage={json.dumps(usage)}", file=sys.stderr)

    out = {
        "refreshed_at": int(time.time()),
        "refreshed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": llm_model(), "provider": llm_provider(),
        "msg_count": len(msgs), "input_chars": total_chars,
        "usage": usage, "latency_sec": round(llm_dt, 2),
        "briefing": {"title": "今日情报简报",
                     "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                     "body": result.get("briefing", "")},
        "focus": result.get("focus", []),
        "actions": result.get("actions", []),
    }
    out_path = os.path.join(ROOT, "llm_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[llm] ✓ wrote {out_path} · focus={len(out['focus'])} · actions={len(out['actions'])}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
