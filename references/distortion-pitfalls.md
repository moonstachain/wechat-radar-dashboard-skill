# Distortion Pitfalls (13 traps the n=1 hit)

If you skip this file you WILL re-discover all 13. They cost real time / real money / real trust during the original build.

## Group A: Build-time identification

### 1. `fork-then-discover` 反模式

We saw `joeseesun/qiaomu-ai-radar` with a beautiful description ("每日选题助手 - 监控 Hacker News / Product Hunt") and assumed it was the right starting point. Cloned it → discovered the repo was **size=0, empty**.

**Rule**: before forking any repo, always `gh api repos/<owner>/<name>/contents` to verify non-empty. Description ≠ code.

### 2. Identification cascade failure

Spent 3 rounds chasing "where is QIAOMU RADAR's source code". Truth was: it didn't exist in any public form. The screenshot was likely a private joeseesun internal product OR built by liming himself prior. Asking the user "is there really a repo?" should have happened at turn 1, not turn 5.

**Rule**: when the user provides a screenshot of "X", **first** verify X exists as code before proposing fork/clone. Cheap question.

## Group B: zsh / macOS environment

### 3. zsh `#` 中文注释陷阱

Pasting:
```
sudo wx init    # 给 sudo 密码 + 内存扫密钥
```
…in zsh **without** `setopt interactive_comments` produces `error: unexpected argument '#' found`. zsh treats `#` as literal arg, passes "# 给 sudo 密码..." to `wx init` as positional args.

**Rule**: NEVER put inline `# 注释` in code blocks you give the user to copy. Put commentary in prose ABOVE the code block. Also: instruct user to run `setopt interactive_comments` if they really want to use commented blocks.

### 4. `codesign --deep --sign` 子组件失败

WeChat 4.x has a sub-component (`ConfSDKdyn.framework`) whose existing signature blocks the deep re-sign. Running:
```bash
sudo codesign --force --deep --sign - /Applications/WeChat.app
```
…fails with `Operation not permitted` on `ConfSDKdyn.framework` alone.

**Fix**: remove the sub-component sig first:
```bash
sudo codesign --remove-signature "/Applications/WeChat.app/Contents/Frameworks/ConfSDKdyn.framework"
sudo codesign --force --deep --sign - /Applications/WeChat.app
```

**Rule**: always pre-document this two-step pattern in the install guide. Don't trust the upstream wx-cli SKILL.md which uses a different sub-component example.

### 5. `~/.wx-cli/daemon.pid` is JSON not int

The pidfile contains:
```json
{"pid":65777,"exe":"/Users/.../wx"}
```
…not just `65777`. `int(open(path).read())` will throw.

**Fix**: try `json.loads()` first, fall back to `int()`.

### 6. `wx daemon status` has no `--json`

It outputs text only: `"wx-daemon 运行中 (PID 65777)"`. The `--json` flag throws `unexpected argument`.

**Fix**: parse the text output OR use the pidfile + `os.kill(pid, 0)` for liveness.

### 7. launchd + `~/Documents/` + bash → TCC trap

macOS TCC blocks `/bin/bash` running under launchd from accessing `~/Documents/`. Even after granting `bash` Full Disk Access, sometimes fails on edge cases.

**Fix**: use Python interpreter directly in plist `ProgramArguments`, not a `.sh` wrapper. Python interpreter is more reliably TCC-friendly when launchd-fired.

## Group C: Web / browser

### 8. `navigator.clipboard.writeText` sandbox denial

In Chromium headless preview (or any non-user-gesture context), `navigator.clipboard.writeText` throws `Write permission denied`. Works fine in real browser user clicks.

**Fix**: wrap in try/catch, surface error via toast. Don't `await` silently — user thinks the copy worked.

### 9. `preview_click` MCP race with screenshot

The MCP `preview_click` returns immediately after dispatching the click. The DOM-rebuild / `render()` from the handler may not have completed before `preview_screenshot` snapshots. You see the **before** state.

**Fix**: when verifying UI changes, use `preview_eval` with `await` chained: `el.click(); await new Promise(r=>setTimeout(r,200));`. Then snapshot.

## Group D: Data semantic / honesty

### 10. mock 数字与 真值 数量级失真

Original mock had `total_messages: 183,504`. Real after stats: `33,359`. **5.5× inflation**.
User trust hit. They thought they had 6× the activity they actually have.

**Rule**: mock data should be **order-of-magnitude honest** for the deployment scale you expect. If unsure, use suspiciously low numbers (`0` or `—`) so user knows it's a placeholder.

### 11. KPI 用 proxy 别假装真

We set `at_me = "count of groups with unread messages"` (proxy) but labeled it "@ 我的". Different semantic. Real was `wx search "@<nick>"` count.

**Rule**: if your KPI is a proxy, **say so explicitly** in subtext ("(proxy from unread groups)") OR fix the real path before shipping.

### 12. sources column showed user themselves

`refresh_stats.py` aggregated `top_senders_cross_group` without filtering SELF. User's own wxid (e.g., `<YOUR_NICK>` in 6 groups + `<your_wxid>` in 3 groups) showed up at top of "情报源" — making the panel useless ("you yourself are the top source of your own intelligence" 🙄).

**Fix**: load `SELF_IDS` from config, filter in script.

### 13. 装饰按钮无声破坏信任

Stage 1 dashboard had 50 interactive-looking buttons. Only `重扫` actually worked. User clicked through, discovered 13 silently did nothing → "this whole thing is fake".

**Fix**: every interactive element MUST be one of:
- 🟢 REAL (does what you'd expect)
- 🟡 HYBRID (does something useful, with explicit subtext explaining the limitation)
- 🚫 PLANNED (explicitly disabled + ⏳ icon + tooltip says "backlog")

NO silently-decorative buttons. Either real, hybrid-with-disclosure, or visibly disabled.

## Anti-pattern: piecemeal patching

After Stage 6, the user said: "做了一堆但点哪个都不灵, 你做一个 audit 然后整体修". The build had drifted into piecemeal: each turn added 1 feature; cumulative result was 26% buttons fake.

**Rule**: at every 3-feature interval, run a **full button audit** (see [50-button-audit.md](50-button-audit.md)). Fix in batches, not one-at-a-time.
