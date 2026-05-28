# DEPLOYMENT — 同事一键部署指南

> 30 分钟内, 你的 Mac 上跑起一个本地微信群聊情报 dashboard.
> 全程不上云, 数据不出本机, 月成本 ~¥15 (LLM 调用费).
>
> 看到这份文档就开始跑, 中间任何报错 → 跳到 [Troubleshooting](#troubleshooting).

---

## ⏱ 时间预算 (按部就班)

| 步骤 | 时长 | 备注 |
|---|---|---|
| 1. Prerequisites 检查 | 5 min | 工具 / 系统检查 |
| 2. 装 wx-cli + sudo wx init | 10 min | **macOS 必须 codesign + 输 sudo 密码** |
| 3. Clone + config.json 填写 | 5 min | 改 3 个字段 |
| 4. 第一次 refresh | 1 min | 8 件套并发跑 |
| 5. 启动 server + 浏览器看 | 2 min | http://localhost:8786 |
| 6. (可选) launchd 自动 refresh | 5 min | 复制 plist + bootstrap |
| **合计** | **~30 min** | 中途有任何报错→ Troubleshooting |

---

## 📦 Step 1: Prerequisites (5 min)

确认本机已有:

```bash
# macOS 版本 (要 11+ Big Sur 或更新)
sw_vers -productVersion

# WeChat 桌面版 (要 4.x)
ls /Applications/WeChat.app

# Node.js (要 ≥ 14, 用于装 wx-cli)
node --version
# 没有? brew install node 或装 nvm

# Python 3 (一般已有, 用于跑所有脚本)
python3 --version

# git
git --version
```

**LLM API key (可选, 没有 dashboard 也能跑, 但少了智能分析层)**:
- DashScope (阿里云通义千问) — **推荐, 中文便宜**, https://dashscope.console.aliyun.com/
- 或 OpenAI / Claude / DeepSeek / Moonshot
- 拿到 key 后 `export DASHSCOPE_API_KEY="sk-..."` 加进你的 `~/.zshrc`

---

## 🔐 Step 2: 装 wx-cli + sudo wx init (10 min)

### 2.1 装 wx-cli (Rust binary, 通过 npm 装)

```bash
npm install -g @jackwener/wx-cli
wx --version    # 验证装上
```

### 2.2 ⚠ macOS 必做: 让 zsh 认中文注释 (避免下一步被坑)

```bash
setopt interactive_comments
```

(否则下一步包含 `# 中文` 的命令会报错 `unexpected argument '#' found`)

### 2.3 给 WeChat 重签名 (允许 wx 进程读 WeChat 内存)

```bash
sudo codesign --remove-signature "/Applications/WeChat.app/Contents/Frameworks/ConfSDKdyn.framework"
sudo codesign --force --deep --sign - /Applications/WeChat.app
```

两条都要 sudo. 第一条**移除子组件原签名** (否则第二条会报 `Operation not permitted`).

### 2.4 重启 WeChat (然后 **手动扫码 / 输密码登录到能看见聊天列表**)

```bash
killall WeChat 2>/dev/null; sleep 2; open /Applications/WeChat.app
```

🛑 **这里停下来**, 让 WeChat 完全登录 (看到你的聊天列表). 下一步 `wx init` 是从已登录的 WeChat 进程内存里抠数据库密钥, 没登录是抠不到的.

### 2.5 sudo wx init (扫描内存提取密钥)

```bash
sudo wx init
```

输你的 **macOS 登录密码** (不是 WeChat 密码, 不是 Apple ID, 终端输入不会显示字符).

成功的标志:
```
检测微信数据目录...
找到 N 个加密数据库
扫描进程内存寻找密钥...
匹配到 N/M 个密钥
密钥已保存: ~/.wx-cli/all_keys.json
配置已保存: ~/.wx-cli/config.json
```

### 2.6 验证 wx-cli 真能读数据

```bash
test -f ~/.wx-cli/config.json && echo "✅ init OK" || echo "❌ init failed"
wx sessions --json | head -30
```

应该看到 JSON 数组, 每条是一个 session.

⚠ **WeChat 升级后**密钥会失效. 重做 2.3 + 2.5 (`sudo wx init --force`).

---

## 📥 Step 3: Clone + config.json (5 min)

```bash
git clone https://github.com/moonstachain/wechat-radar-dashboard-skill.git \
  ~/Documents/wechat-radar-dashboard

cd ~/Documents/wechat-radar-dashboard

# 复制模板
cp config.example.json config.json
```

打开 `config.json` 用你的编辑器, 改 **3 个必填字段**:

```json
{
  "brand": "MY RADAR",                  // ← 改成你想要的侧栏品牌字 (例 "工作雷达" / "情报站")
  "self_ids": [
    "你在微信里的显示名",                   // ← 必填. 群里 @ 你时看到的名字
    "your_wxid"                          // ← 你的 wxid (在 WeChat 设置看)
  ],
  "at_queries": [
    "@你在微信里的显示名"                  // ← 必填. 用于 wx search "@xxx" 计数
  ],
  "llm": {
    "provider": "dashscope",             // dashscope / openai / claude / deepseek / moonshot
    "model": "qwen-plus",
    "api_key_env": "DASHSCOPE_API_KEY",   // ← 你 export 在 ~/.zshrc 里的环境变量名
    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
  }
}
```

**怎么找你的 self_ids**:
1. 打开任意一个你在的群, 看自己消息下方显示的昵称 → 这是 self_ids 第一个
2. WeChat 设置 → 微信号 → 复制下来 → 这是 self_ids 第二个 (有时跟昵称不同)

---

## ⚡ Step 4: 第一次 refresh (1 min)

```bash
python3 scripts/launch_refresh.py
```

依次跑 9 件套:
1. refresh_stats — wx stats 聚合 (~4s)
2. refresh_links — wx history --type link (~3s)
3. refresh_mentions — wx search @你 (~2s)
4. refresh_replies — 未回复积压检测 (~3s)
5. refresh_official — wx biz-articles 公众号 (~1s)
6. refresh_private — 1-on-1 私聊 (~3s)
7. refresh_self — 自我角色镜子 (~3s)
8. refresh_unified — 跨源同人物归一 (~0s)
9. llm_classify — qwen-plus 智能分析 (~25s, ~¥0.17)

**总计 ~45s + ¥0.17**. 看到每一步的 `✓` 表示成功.

⚠ 如果 llm_classify 报 `API key not found` → 检查 config.json 的 api_key_env 字段跟你 `~/.zshrc` 的 export 名字一致.

---

## 🌐 Step 5: 启动 server (2 min)

```bash
python3 scripts/server.py
```

终端会显示:
```
[wx-dash] serving frontend=... on http://127.0.0.1:8786
[wx-dash] wx binary: /Users/.../wx
[wx-dash] brand: {'brand': 'YOUR_BRAND', 'tagline': '...'}
[wx-dash] initial mode = real-full
```

浏览器打开 **http://localhost:8786**

应该看到:
- 顶部 badge: 🟢 `wx-cli + qwen · live`
- 4 KPI 真数字 (活跃群 / 总消息 / @ 我的 / 静默群)
- 简报 + SCQA + MECE 5 议题 + 3 列焦点
- 左侧 sidebar: 看板/信号流/话题雷达/链接情报 + 收藏/未分组/私聊/公众号/我的镜子

🎉 装好了.

---

## 🔁 Step 6: launchd 自动刷新 (5 min, 可选)

让 dashboard 每天自动 fire 3 次 (07:30 / 12:30 / 19:30):

```bash
# 1. 把 plist 模板里的占位符替换成你的真实路径
sed -i '' "s|YOUR_USER|$(whoami)|g; s|YOUR_PROJECT_DIR|$HOME/Documents/wechat-radar-dashboard|g" \
  scripts/com.example.wxradar.refresh.plist

# 2. 安装
cp scripts/com.example.wxradar.refresh.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.wxradar.refresh.plist
launchctl enable gui/$(id -u)/com.example.wxradar.refresh

# 3. 立即测试 fire (~45s, ~¥0.17)
launchctl kickstart -k gui/$(id -u)/com.example.wxradar.refresh
tail -f launchd.out.log
```

⚠ macOS TCC FDA 陷阱: 如果 `launchd.err.log` 报 "Operation not permitted" 写文件失败:
- System Settings → Privacy & Security → Full Disk Access → 加 `/opt/homebrew/bin/python3` (或 `which python3` 的实际路径)

---

## 🛠 Troubleshooting

### `wx-daemon 启动超时`
- `cat ~/.wx-cli/daemon.log` 看真因
- 多数: WeChat 升级后 codesign 失效 → 重做 Step 2.3 + 2.5

### `~/.wx-cli/config.json` 不存在
- Step 2.5 `sudo wx init` 没真跑通
- 看 daemon.log 找原因 (常是: WeChat 未登录 / codesign 没做)

### LLM API key not found
- `echo $DASHSCOPE_API_KEY` 是空? → 加到 `~/.zshrc` 然后 `source ~/.zshrc`
- 或直接 `export DASHSCOPE_API_KEY="sk-..."` 当前 shell 试

### dashboard 顶部 badge 是黄色 `mock`
- `/api/data` 返回 mock 数据, 说明 wx 调用失败
- 浏览器开 DevTools → Network → `/api/data` 看 `_error` 字段
- 多数: wx-daemon 没起来 → `wx daemon stop && wx sessions --json` (自动重启 daemon)

### KPI 数字与你 WeChat 实际不一致
- 这是 `wx stats` 默认 30 天窗口. 切上方 "日/周/月/季/年" segment 看不同窗口
- 总消息数包含 mock 加 stats 真值. mute 候选 / 公众号 是 30d 窗口

### `navigator.clipboard.writeText` denied
- Chrome / Safari 在某些 context 拒绝剪贴板. 真用户点击通常 OK, headless 模式拒
- 影响: 复制摘要 / 焦点条复制 失败. dashboard 主功能正常

### 想换 LLM (e.g. 改用 Claude / OpenAI)
- 改 config.json 的 llm.provider / model / endpoint / api_key_env
- 重跑 `python3 scripts/llm_classify.py` 验证

### Dashboard 上看到敏感词 (赌/扑克/poker 等)
- server.py 有 EXCLUDED_RE 自动过滤. 如有遗漏:
- 加词进 config.json → `"excluded_keywords": ["你的词", ...]`
- 重启 server 生效

---

## 📊 月成本 / 隐私契约

| 项 | 成本 | 数据走向 |
|---|---|---|
| wx stats / links / mentions / replies / official / private / self / unified | 0 ¥ | 全本地 wx-cli (Rust 调本机解密 DB) |
| llm_classify | ~¥0.17 / 次 (qwen-plus). 3 次/天 = ~¥0.51/天 | 过滤后的文本 (无 XML / 媒体) 发到你选的 LLM 厂商 |
| Server | 0 | 监听 127.0.0.1 only, **不暴露公网** |
| GitHub mirror | 0 | 仅代码, 所有 `*.json` 数据缓存都 gitignore |

**月成本: ~¥15 + 0 chat 泄漏风险.**

---

## 🚫 数据不会做的事

- 不会自动给任何人发消息 (read-only)
- 不会同步到云端 dashboard (本机 only)
- 不会自动执行 LLM 识别的"行动项" (你看完手动做)
- 不会保留你的 WeChat 历史超过 wx-cli 已有的 (wx-cli 不写, 只读)

---

## 🎓 进阶用法

### 切换窗口 (顶部 segment 日/周/月/季/年)
- 真后端重查 (LLM stay 24h 固定, KPI 跟随窗口变)

### 自定义 collections (手动选群)
- 创建 `collections.json` (root dir):
  ```json
  [
    {"dot": "#a3e635", "name": "你想固定显示的群名", "n": 0}
  ]
  ```
- 覆盖默认按消息量 top 14 自动选

### 自定义 LLM prompt
- 改 `scripts/llm_classify.py` 的 `SYSTEM` 和 `build_user_prompt`
- 推荐: 改 role description ("我是投资经理 / 内容创作者 / 创业者...")

### 加你自己的关注词到 mute / focus 过滤
- 改 `scripts/refresh_stats.py` 的 mute_candidates 条件
- 改 `scripts/llm_classify.py` prompt 的"跳过下列群"列表

---

## 🆘 装不上时

GitHub Issues: https://github.com/moonstachain/wechat-radar-dashboard-skill/issues

带上以下信息:
- macOS 版本 + WeChat 版本
- 是哪一步失败 (Step 2.x / 3.x / etc)
- 完整错误日志 (DO NOT 贴你的 self_ids / API key 等真实凭证)

---

**Have fun! 🎯**
