#!/usr/bin/env python3
"""wx-radar-dashboard server (Python stdlib only).

Endpoints:
  GET /                  -> static (../frontend/index.html, etc.)
  GET /api/config        -> brand / tagline (so frontend can render user's brand)
  GET /api/health        -> {mode, last_refresh, error, wx_path}
  GET /api/data          -> dashboard payload (mock fallback if wx-cli failed)
     Query params:
       ?days=N           -> override window (1/7/30/90/365)
       ?date=YYYY-MM-DD  -> snapshot date label only
       ?mode=auto|hour|day|week  -> echoed
  GET /api/refresh       -> force fetch_real() (server cache only)
  GET /api/all-groups    -> top 100 groups for drawer
  GET /api/favorites     -> wx favorites for drawer
  GET /api/daemon-status -> real wx daemon PID + uptime
  POST /api/launchd-fire -> launchctl kickstart (~30-60s + LLM cost)
"""
import json
import os
import subprocess
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT, "frontend")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
from _config import CONFIG, brand as _brand  # noqa

PORT = int(os.environ.get("PORT", (CONFIG.get("server") or {}).get("port", 8786)))
HOST = (CONFIG.get("server") or {}).get("host", "127.0.0.1")
TTL_SECONDS = (CONFIG.get("server") or {}).get("cache_ttl_seconds", 60)
WX_TIMEOUT = 20
DEFAULT_DAYS = (CONFIG.get("windows") or {}).get("stats_days", 30)

_cache: dict = {}
_aux_cache: dict = {}


def _run_wx(args, timeout=WX_TIMEOUT):
    r = subprocess.run(["wx", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200])
    return json.loads(r.stdout)


def _unwrap(resp, keys=("sessions", "data", "items", "unread", "matches", "results", "messages", "favorites")):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in keys:
            if k in resp and isinstance(resp[k], list):
                return resp[k]
    return []


def _ts(s):
    v = (s.get("timestamp") or s.get("last_message_time") or s.get("last_message_ts") or 0)
    if isinstance(v, str):
        try:
            return int(time.mktime(time.strptime(v[:19], "%Y-%m-%d %H:%M:%S")))
        except Exception:
            return 0
    if v > 10_000_000_000:
        v //= 1000
    return int(v)


def fetch_real(days=DEFAULT_DAYS):
    sessions = _unwrap(_run_wx(["sessions", "-n", "500"]))
    try:
        unread_items = _unwrap(_run_wx(["unread", "--filter", "group"]))
    except Exception:
        unread_items = []
    groups = [s for s in sessions if s.get("chat_type") == "group"]
    now = int(time.time())
    cutoff = now - days * 86400
    n_total = len(groups)
    n_active = sum(1 for g in groups if _ts(g) > cutoff)
    n_silent = max(0, n_total - n_active)
    n_unread_groups = len(unread_items)
    total_unread = sum(int(x.get("unread") or 0) for x in unread_items)

    # Mock fallback baseline
    with open(os.path.join(FRONTEND_DIR, "mock_data.json"), encoding="utf-8") as f:
        d = json.load(f)
    d["kpi"] = {**d["kpi"], "active_groups": n_active, "total_groups": n_total,
                "at_me": n_unread_groups, "silent": n_silent, "window_hours": days * 24}
    d["_mode"] = "real-kpi-only"
    d["_real_fields"] = ["active_groups", "total_groups", "at_me", "silent"]
    d["_extras"] = {"unread_groups": n_unread_groups, "unread_msgs_total": total_unread,
                    "sample_size": len(sessions), "param_days": days}

    # collections (default = top groups by msg; user-supplied collections.json overrides)
    coll_file = os.path.join(ROOT, "collections.json")
    palette = ["#c084fc","#86efac","#67e8f9","#c4b5fd","#fde047","#fbbf24","#fca5a5","#d6b88a"]
    if os.path.exists(coll_file):
        d["collections"] = json.load(open(coll_file, encoding="utf-8"))
        d["_real_fields"].append("collections")
    else:
        named = [g for g in groups if g.get("chat") and not g["chat"].endswith("@chatroom")]
        named.sort(key=lambda g: (int(g.get("unread") or 0), _ts(g)), reverse=True)
        d["collections"] = [
            {"dot": palette[i % len(palette)], "name": g["chat"][:22],
             "n": int(g.get("unread") or 0)} for i, g in enumerate(named[:14])
        ]
        d["_real_fields"].append("collections")

    # merge mentions.json
    ment = os.path.join(ROOT, "mentions.json")
    if os.path.exists(ment):
        try:
            mt = json.load(open(ment, encoding="utf-8"))
            ms_windows = mt.get("windows", {})
            window_key = f"{days}d"
            if window_key in ms_windows:
                d["kpi"]["at_me"] = ms_windows[window_key]
                d["kpi"]["at_me_window_days"] = days
            else:
                d["kpi"]["at_me"] = mt.get("n_total", 0)
                d["kpi"]["at_me_window_days"] = mt.get("window_days", 7)
            d["kpi"]["at_me_unique_groups"] = mt.get("n_unique_groups", 0)
            d["_real_fields"].append("at_me_real")
            d["_extras"].update({
                "mentions_refreshed_at": mt.get("refreshed_at_human"),
                "mentions_age_sec": int(time.time() - mt.get("refreshed_at", 0)),
                "mentions_windows": ms_windows,
                "mentions_by_group": mt.get("by_group"),
                "mentions_by_sender": mt.get("by_sender"),
                "mentions_recent": mt.get("recent"),
            })
        except Exception as e:
            d["_extras"]["mentions_err"] = str(e)

    # merge stats.json
    sf = os.path.join(ROOT, "stats.json")
    if os.path.exists(sf):
        try:
            deep = json.load(open(sf, encoding="utf-8"))
            d["kpi"]["total_messages"] = deep.get("total_messages")
            d["kpi"]["total_messages_window_days"] = deep.get("window_days", 30)
            d["kpi"]["avg_per_group"] = deep.get("avg_per_group")
            d["_real_fields"].extend(["total_messages", "avg_per_group", "sources"])
            d["_extras"].update({
                "stats_refreshed_at": deep.get("refreshed_at_human"),
                "stats_age_sec": int(time.time() - deep.get("refreshed_at", 0)),
                "by_type": deep.get("by_type"),
                "window_days": deep.get("window_days"),
            })
            if deep.get("top_senders_cross_group"):
                d["sources"] = deep["top_senders_cross_group"]
            if not os.path.exists(coll_file) and deep.get("top_groups_by_msgs"):
                top = [g for g in deep["top_groups_by_msgs"]
                       if g.get("chat") and not g["chat"].endswith("@chatroom")][:14]
                d["collections"] = [
                    {"dot": palette[i % len(palette)], "name": g["chat"][:22],
                     "n": int(g.get("total") or 0)} for i, g in enumerate(top)
                ]
        except Exception as e:
            d["_extras"]["stats_err"] = str(e)

    # merge links.json
    lf = os.path.join(ROOT, "links.json")
    if os.path.exists(lf):
        try:
            lk = json.load(open(lf, encoding="utf-8"))
            d["links_aggregated"] = lk.get("links", [])
            d["_real_fields"].append("links_aggregated")
            d["_extras"].update({
                "links_refreshed_at": lk.get("refreshed_at_human"),
                "links_window_days": lk.get("window_days"),
                "links_n_unique": lk.get("n_links_unique"),
                "links_summary": lk.get("summary"),
                "links_age_sec": int(time.time() - lk.get("refreshed_at", 0)),
            })
        except Exception as e:
            d["_extras"]["links_err"] = str(e)

    # merge llm_output.json
    llf = os.path.join(ROOT, "llm_output.json")
    if os.path.exists(llf):
        try:
            llm = json.load(open(llf, encoding="utf-8"))
            if llm.get("briefing"): d["briefing"] = llm["briefing"]
            if llm.get("focus"):    d["focus"] = llm["focus"]
            if llm.get("actions"):  d["actions"] = llm["actions"]
            d["_real_fields"].extend(["briefing", "focus", "actions"])
            d["_extras"].update({
                "llm_refreshed_at": llm.get("refreshed_at_human"),
                "llm_model": llm.get("model"),
                "llm_provider": llm.get("provider"),
                "llm_age_sec": int(time.time() - llm.get("refreshed_at", 0)),
                "llm_msg_count": llm.get("msg_count"),
                "llm_usage": llm.get("usage"),
            })
            d["_mode"] = "real-full"
        except Exception as e:
            d["_extras"]["llm_err"] = str(e)
    return d


def fetch_mock():
    with open(os.path.join(FRONTEND_DIR, "mock_data.json"), encoding="utf-8") as f:
        d = json.load(f)
    d["_mode"] = "mock"
    return d


def get_data(force=False, days=DEFAULT_DAYS):
    now = time.time()
    entry = _cache.get((days,))
    if not force and entry and (now - entry["ts"]) < TTL_SECONDS:
        return entry["data"]
    try:
        d = fetch_real(days=days)
        _cache[(days,)] = {"data": d, "ts": now, "mode": d["_mode"], "error": None}
    except Exception as e:
        d = fetch_mock()
        d["_error"] = f"{type(e).__name__}: {e}"
        _cache[(days,)] = {"data": d, "ts": now, "mode": "mock", "error": str(e)}
    return _cache[(days,)]["data"]


def aux_all_groups(force=False):
    if not force and (e := _aux_cache.get("all_groups")) and time.time() - e["ts"] < 300:
        return e["data"]
    try:
        sessions = _unwrap(_run_wx(["sessions", "-n", "500"]))
        groups = [s for s in sessions if s.get("chat_type") == "group"]
        groups.sort(key=_ts, reverse=True)
        data = {"n": len(groups), "ts": int(time.time()),
                "groups": [{"chat": (g.get("chat") or g.get("username") or "?")[:36],
                            "username": g.get("username", ""), "unread": int(g.get("unread") or 0),
                            "time": g.get("time", ""), "timestamp": g.get("timestamp", 0),
                            "last_sender": g.get("last_sender", ""),
                            "last_msg_type": g.get("last_msg_type", ""),
                            "summary": (g.get("summary") or "")[:80]}
                           for g in groups[:100]]}
    except Exception as e:
        data = {"n": 0, "groups": [], "error": str(e)}
    _aux_cache["all_groups"] = {"data": data, "ts": time.time()}
    return data


def aux_favorites(force=False):
    if not force and (e := _aux_cache.get("favorites")) and time.time() - e["ts"] < 300:
        return e["data"]
    try:
        items = _unwrap(_run_wx(["favorites"]))
        data = {"n": len(items), "ts": int(time.time()),
                "items": [{"type": x.get("type", "?"),
                           "title": (x.get("title") or x.get("content") or "")[:120],
                           "des": (x.get("des") or "")[:120],
                           "source": x.get("source") or x.get("from") or "",
                           "time": x.get("time", ""), "timestamp": x.get("timestamp", 0)}
                          for x in items[:100]]}
    except Exception as e:
        data = {"n": 0, "items": [], "error": str(e)}
    _aux_cache["favorites"] = {"data": data, "ts": time.time()}
    return data


def aux_daemon_status():
    """Real wx-daemon status. Notes:
       · `wx daemon status` 没 --json, 输出是文本
       · ~/.wx-cli/daemon.pid 是 JSON {pid, exe} 不是裸 int
    """
    pid, exe = None, None
    pid_path = os.path.expanduser("~/.wx-cli/daemon.pid")
    if os.path.exists(pid_path):
        try:
            obj = json.loads(open(pid_path).read().strip())
            pid = int(obj.get("pid")) if obj.get("pid") else None
            exe = obj.get("exe")
        except Exception:
            pass
    alive = False
    if pid:
        try:
            os.kill(pid, 0); alive = True
        except Exception:
            pass
    text = None
    try:
        r = subprocess.run(["wx", "daemon", "status"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            text = r.stdout.strip()
    except Exception as e:
        text = f"(error: {e})"
    return {"running": alive, "pid": pid, "exe": exe, "status_text": text,
            "pid_file_mtime": int(os.path.getmtime(pid_path)) if os.path.exists(pid_path) else None,
            "ts": int(time.time())}


def aux_launchd_fire():
    # NOTE: user must have installed plist + given it a Label; we read from config.
    plist_label = (CONFIG.get("server") or {}).get("launchd_label", "com.example.wxradar.refresh")
    try:
        uid = os.getuid()
        cmd = ["launchctl", "kickstart", "-k", f"gui/{uid}/{plist_label}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {"ok": r.returncode == 0,
                "stdout": r.stdout.strip()[:200],
                "stderr": r.stderr.strip()[:200],
                "label": plist_label,
                "msg": f"launchd job '{plist_label}' triggered. Wait ~30-60s, then refresh."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _which(cmd):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        f = os.path.join(d, cmd)
        if os.path.isfile(f) and os.access(f, os.X_OK):
            return f
    return None


class H(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write(f"[wx-dash] {fmt % a}\n")

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path); p = u.path; q = parse_qs(u.query)
        if p == "/api/config":
            return self._json(_brand())
        if p == "/api/health":
            get_data()
            entry = _cache.get((DEFAULT_DAYS,)) or {}
            return self._json({"mode": entry.get("mode"), "last_refresh": int(entry.get("ts", 0)),
                               "error": entry.get("error"), "wx_path": _which("wx")})
        if p == "/api/data":
            try: days = int(q.get("days", [DEFAULT_DAYS])[0])
            except ValueError: days = DEFAULT_DAYS
            days = max(1, min(days, 730))
            data = get_data(days=days)
            data["_query"] = {"days": days, "date": q.get("date", [None])[0],
                              "mode": q.get("mode", ["auto"])[0]}
            return self._json(data)
        if p == "/api/refresh":
            try: days = int(q.get("days", [DEFAULT_DAYS])[0])
            except ValueError: days = DEFAULT_DAYS
            get_data(force=True, days=days)
            entry = _cache.get((days,)) or {}
            return self._json({"ok": True, "mode": entry.get("mode"), "error": entry.get("error")})
        if p == "/api/all-groups":
            return self._json(aux_all_groups(force=q.get("force", ["0"])[0] in ("1","true")))
        if p == "/api/favorites":
            return self._json(aux_favorites(force=q.get("force", ["0"])[0] in ("1","true")))
        if p == "/api/daemon-status":
            return self._json(aux_daemon_status())
        if p == "/api/launchd-fire":
            return self._json(aux_launchd_fire())
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path == "/api/launchd-fire":
            return self._json(aux_launchd_fire())
        self.send_error(405)

    def translate_path(self, path):
        p = urlparse(path).path.lstrip("/") or "index.html"
        return os.path.join(FRONTEND_DIR, p)


def main():
    os.chdir(ROOT)
    print(f"[wx-dash] serving frontend={FRONTEND_DIR} on http://{HOST}:{PORT}", file=sys.stderr)
    print(f"[wx-dash] wx binary: {_which('wx') or '(not found)'}", file=sys.stderr)
    print(f"[wx-dash] brand: {_brand()}", file=sys.stderr)
    try:
        get_data()
        entry = _cache.get((DEFAULT_DAYS,)) or {}
        print(f"[wx-dash] initial mode = {entry.get('mode')}", file=sys.stderr)
        if entry.get("error"):
            print(f"[wx-dash] (fallback) {entry['error']}", file=sys.stderr)
    except Exception as e:
        print(f"[wx-dash] warm failed: {e}", file=sys.stderr)
    HTTPServer((HOST, PORT), H).serve_forever()


if __name__ == "__main__":
    main()
