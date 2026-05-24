#!/usr/bin/env python3
"""launch_refresh.py — launchd entrypoint, runs 4 refresh scripts in sequence.

Why Python (not bash):
  · launchd + /bin/bash + ~/Documents/ triggers macOS TCC Full Disk Access wall.
    Python interpreter is more reliably TCC-friendly.
  · Still may need to grant FDA to /opt/homebrew/bin/python3 if writes to ~/Documents/ fail.

Total ~30-60s per fire (LLM dominant). Cost: ~¥0.17 per fire (LLM only).

Install: see ../com.example.wxradar.refresh.plist template.
"""
import os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))

# ─── load env from shell rc (launchd has no shell env) ─────────────────
for rc in ("~/.zshrc", "~/.zshenv", "~/.zprofile", "~/.bashrc"):
    p = os.path.expanduser(rc)
    if not os.path.exists(p): continue
    try:
        with open(p, encoding="utf-8") as fp:
            for line in fp:
                m = re.match(r'\s*export\s+([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]+?)"?\s*$', line)
                if not m: continue
                key, val = m.group(1), m.group(2)
                if any(s in key for s in ("KEY","TOKEN","SECRET","API","PATH","HOST")):
                    os.environ.setdefault(key, val.strip('"').strip("'"))
    except Exception:
        continue

# ─── ensure wx (npm global) on PATH ────────────────────────────────────
for cand in ("~/.nvm/versions/node/v24.14.1/bin","~/.nvm/versions/node/v22.0.0/bin",
             "/opt/homebrew/bin","/usr/local/bin"):
    d = os.path.expanduser(cand)
    if os.path.isdir(d) and d not in os.environ.get("PATH",""):
        os.environ["PATH"] = f"{d}:{os.environ.get('PATH','')}"

print(f"\n=========================================", flush=True)
print(f"[wx-dash refresh] {time.strftime('%Y-%m-%d %H:%M:%S %Z')}", flush=True)
print(f"  PATH (head): {os.environ.get('PATH','')[:120]}", flush=True)

scripts = [
    ("refresh_stats.py",    []),
    ("refresh_links.py",    []),
    ("refresh_mentions.py", []),
    ("llm_classify.py",     []),
]
codes = []
t_total = time.time()
for name, args in scripts:
    print(f"\n--- {name} ---", flush=True)
    t = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, name), *args], cwd=HERE)
    codes.append(r.returncode)
    print(f"--- exit={r.returncode} · {time.time()-t:.1f}s ---", flush=True)

print(f"\n[wx-dash refresh] total {time.time()-t_total:.1f}s · {dict(zip([s[0] for s in scripts], codes))}",
      flush=True)
sys.exit(next((c for c in codes if c != 0), 0))
