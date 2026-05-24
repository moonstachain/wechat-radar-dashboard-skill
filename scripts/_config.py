"""Shared config loader for all refresh_*.py + llm_classify.py.

Reads ROOT/config.json (NOT in git). Falls back to config.example.json if missing.
"""
import json
import os

# ROOT = parent of scripts/ = project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict:
    """Try config.json (user's), fall back to config.example.json (template).
    Either way returns dict. User-real values needed for self_ids / at_queries.
    """
    for fn in ("config.json", "config.example.json"):
        path = os.path.join(ROOT, fn)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(
        f"No config.json or config.example.json found in {ROOT}. "
        f"Copy config.example.json → config.json and fill in your self_ids."
    )


CONFIG = load_config()


def self_ids() -> tuple[str, ...]:
    return tuple(CONFIG.get("self_ids", []))


def at_queries() -> list[str]:
    return CONFIG.get("at_queries", [])


def llm_provider() -> str:
    return (CONFIG.get("llm") or {}).get("provider", "dashscope")


def llm_model() -> str:
    return (CONFIG.get("llm") or {}).get("model", "qwen-plus")


def llm_api_key() -> str | None:
    """Read from env first; fall back to ~/.zshrc parsing."""
    env_name = (CONFIG.get("llm") or {}).get("api_key_env", "DASHSCOPE_API_KEY")
    k = os.environ.get(env_name)
    if k:
        return k
    # Fallback: parse from common shell rc
    import re
    for f in ("~/.zshrc", "~/.zshenv", "~/.zprofile", "~/.bashrc"):
        p = os.path.expanduser(f)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as fp:
                for line in fp:
                    m = re.match(rf'\s*export\s+{env_name}\s*=\s*"?([^"\s]+)"?', line)
                    if m:
                        return m.group(1)
        except Exception:
            continue
    return None


def llm_endpoint() -> str:
    cfg = CONFIG.get("llm") or {}
    if cfg.get("endpoint"):
        return cfg["endpoint"]
    provider = llm_provider()
    return {
        "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "openai":    "https://api.openai.com/v1/chat/completions",
        "claude":    "https://api.anthropic.com/v1/messages",
        "deepseek":  "https://api.deepseek.com/v1/chat/completions",
        "moonshot":  "https://api.moonshot.cn/v1/chat/completions",
    }.get(provider, "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")


def llm_temperature() -> float:
    return float((CONFIG.get("llm") or {}).get("temperature", 0.3))


def windows() -> dict:
    return CONFIG.get("windows", {
        "stats_days": 30, "links_days": 30, "mentions_days": 7, "llm_hours": 24
    })


def brand() -> dict:
    return {
        "brand": CONFIG.get("brand", "MY RADAR"),
        "tagline": CONFIG.get("tagline", "私有看板 · 高信号优先"),
    }
