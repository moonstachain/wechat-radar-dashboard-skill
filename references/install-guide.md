# Install Guide

## Prerequisites

1. macOS (Apple Silicon or Intel)
2. WeChat desktop 4.x installed and logged in
3. Node.js ≥ 14 (for npm install path) OR curl (for shell install)
4. Sudo access (for one-time `wx init` memory scan)
5. (Optional) LLM API key for intelligence layer: DashScope / OpenAI / Claude / DeepSeek / Moonshot

## Step 1: Install wx-cli

```bash
npm install -g @jackwener/wx-cli
# Or:
curl -fsSL https://raw.githubusercontent.com/jackwener/wx-cli/main/install.sh | bash
```

Verify:
```bash
wx --version
```

## Step 2: One-time wx init (CRITICAL — must succeed before anything works)

### 2.1 Enable zsh comments (so you can paste commands without # being eaten)

```
setopt interactive_comments
```

⚠ Without this, any pasted command with a trailing `# comment` will fail. zsh
treats `#` as literal unless this option is on.

### 2.2 codesign WeChat (so wx can attach to its process)

```
sudo codesign --remove-signature "/Applications/WeChat.app/Contents/Frameworks/ConfSDKdyn.framework"
sudo codesign --force --deep --sign - /Applications/WeChat.app
```

⚠ **Why two commands**: the first removes a sub-component signature that blocks
the `--deep --sign` from succeeding. If you just run the second one, you'll see
`Operation not permitted` on `ConfSDKdyn.framework`.

⚠ **Why sudo**: the install path `/Applications/WeChat.app` requires elevated
write access. Without sudo: `Permission denied`.

Both commands should produce **no output** on success.

### 2.3 Restart WeChat and log back in

```
killall WeChat 2>/dev/null; sleep 2; open /Applications/WeChat.app
```

⚠ **WAIT HERE** — manually scan QR / enter password to log into WeChat. Confirm
you can see your chat list. `wx init` reads the running WeChat process's memory,
so WeChat must be fully logged in first.

### 2.4 Run init

```
sudo wx init
```

Enter your **macOS login password** when prompted. (Not WeChat password, not
Apple ID — your Mac login password. The terminal won't show typed characters.)

On success you'll see:
```
检测微信数据目录...
找到数据目录: ...
扫描进程内存寻找密钥...
找到 N 个候选密钥
匹配到 N/M 个密钥
成功提取 N 个数据库密钥
密钥已保存: /Users/YOU/.wx-cli/all_keys.json
配置已保存: /Users/YOU/.wx-cli/config.json
```

### 2.5 Verify

```
test -f ~/.wx-cli/config.json && echo "✅ init 成功" || echo "❌ 还是没成"
wx sessions --json | head -20
```

Should see a JSON array of session objects.

⚠ **WeChat upgrades** will invalidate the signature. After every WeChat update:
1. Re-run step 2.2 (codesign)
2. Re-run step 2.4 (`sudo wx init --force`)

## Step 3: Deploy the dashboard

```bash
git clone https://github.com/moonstachain/wechat-radar-dashboard-skill.git ~/Documents/wechat-radar-dashboard
cd ~/Documents/wechat-radar-dashboard
```

## Step 4: Configure

```bash
cp config.example.json config.json
vim config.json  # or your editor
```

**Minimum required fields**:
- `brand`: any string for sidebar (e.g., "WORK RADAR")
- `self_ids`: array of your WeChat display names + wxid (used to filter your own messages from `sources` column and `@me` count)
- `at_queries`: array of `@<nick>` patterns (used by `refresh_mentions.py` for wx search)
- `llm.api_key_env`: name of the env var holding your LLM key (e.g., `DASHSCOPE_API_KEY`)

**Find your self_ids**:
1. Run `wx contacts --query <your-nick>` — see what name shows up
2. Open any group you're in via WeChat app — see what nick appears under your messages
3. Both go in `self_ids`

## Step 5: First refresh (populate caches)

```bash
python3 scripts/refresh_stats.py
python3 scripts/refresh_links.py
python3 scripts/refresh_mentions.py
python3 scripts/llm_classify.py    # only if you have LLM key set
```

Or all 4 at once:
```bash
python3 scripts/launch_refresh.py
```

Should take ~30-60s total. ¥0.17 (LLM portion only).

## Step 6: Start server

```bash
python3 scripts/server.py
```

Open http://localhost:8786. Should see your brand text + lime "wx-cli + qwen · live" badge.

## Step 7 (optional): launchd auto-refresh

```bash
# 1. Template-replace the plist
sed -i '' "s|YOUR_USER|$(whoami)|g; s|YOUR_PROJECT_DIR|$HOME/Documents/wechat-radar-dashboard|g" \
  scripts/com.example.wxradar.refresh.plist

# 2. Install
cp scripts/com.example.wxradar.refresh.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.wxradar.refresh.plist
launchctl enable gui/$(id -u)/com.example.wxradar.refresh

# 3. Test fire
launchctl kickstart -k gui/$(id -u)/com.example.wxradar.refresh
tail -f launchd.out.log
```

## Step 8 (optional): Server auto-start

For now, run `python3 scripts/server.py` manually in a terminal or screen/tmux.

A separate launchd plist for the server is backlog (planned but not in skill).
Quick workaround:

```bash
nohup python3 scripts/server.py > server.log 2>&1 &
disown
```

## Troubleshooting

### `wx-daemon 启动超时`

- Check `~/.wx-cli/daemon.pid` — if PID doesn't exist as a process, delete the file and retry
- Read `~/.wx-cli/daemon.log` for actual reason
- Common: WeChat upgrade invalidated codesign — redo steps 2.2 + 2.4

### `LLM API key not found`

- Check `config.json` → `llm.api_key_env` matches your actual env var name
- Run `echo $DASHSCOPE_API_KEY` (or whatever name) — if empty, add `export X=...` to `~/.zshrc`
- `launch_refresh.py` reads from `~/.zshrc` automatically; you don't need to source it manually

### Server starts but dashboard blank

- Open browser DevTools → Network → `/api/data` response — should be JSON
- Check `_mode` in response: `real-full` ✅ / `mock` = wx-daemon down / `inline` = server unreachable
- If `mock`: see "wx-daemon 启动超时" above

### Segment 日/周/月 switch doesn't change KPI

- `/api/data?days=7` should return different numbers than `/api/data?days=1`
- If same → check `server.py` is the new version (with `days` param support)
- Hard refresh browser (Cmd+Shift+R)

### `navigator.clipboard.writeText` denied

- Browser sandbox issue (some Chromium contexts deny clipboard without user gesture)
- Works fine in normal Chrome/Safari user clicks
- Test by clicking 复制摘要 button manually (not via eval)
