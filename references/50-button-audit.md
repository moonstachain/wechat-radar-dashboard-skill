# 50-Button Audit Framework

Apply this to your dashboard build at every 3-feature interval. Catches silent
broken-ness before it accumulates and destroys user trust.

## The 4-status model

Every interactive element falls in one of 4 buckets:

| Status | Symbol | Meaning | User expectation |
|---|---|---|---|
| **REAL** | 🟢 | Click → real action happens. UI reflects real backend state. | Just works |
| **HYBRID** | 🟡 | Click → action happens but has a documented limitation. Subtext explains. | Works partially, knows why |
| **PLANNED** | 🚫 | Disabled. ⏳ icon. Tooltip says "backlog". | Knows not to expect anything |
| **DECORATIVE** | 🔴 | Looks clickable but does nothing. **FORBIDDEN.** Must be converted to one of above. | Click → nothing happens → trust shattered |

Goal: **0 elements in DECORATIVE state at any time.**

## The audit template

For every interactive element in your dashboard, fill in this row:

```
| # | Location | Element | Click action | Data source | Status |
|---|---|---|---|---|---|
| 1 | sidebar top | brand label | (none, decorative) | static | ⚪ pure decoration (OK) |
| 2 | sidebar | settings gear | open settings drawer | /api/config + state | 🟢 REAL |
| 3 | header | range "日" segment | reload data with ?days=1 | /api/data?days=1 | 🟢 REAL |
| 4 | header | range "自定义" segment | (no date-range UI yet) | n/a | 🚫 PLANNED (disabled + ⏳) |
...
```

## Audit checklist (50-row template)

Run this for the wechat-radar-dashboard each major release. Adapt rows for your build.

### Sidebar (top to bottom)

- [ ] 1. Brand label — decorative, OK
- [ ] 2. Settings gear icon — opens settings drawer? real config shown?
- [ ] 3-6. 4 main nav tabs (Brief/Live/Cross/Link) — switch view? content real?
- [ ] 7. 所有群 — opens drawer? lists real groups?
- [ ] 8. 收藏 — opens drawer? `wx favorites` returns real items?
- [ ] 9. 未分组 — opens drawer? count is real (total - in-collections)?
- [ ] 10-23. 14 collections — click → filter focus/actions to that group? badge appears?
- [ ] 24. daemon footer — shows real PID? click → drawer with status text?

### Header (top right)

- [ ] 25. View title — updates with view switch?
- [ ] 26. Mode badge — reflects `_mode` from /api/data?
- [ ] 27. Filter badge × — clears filter?
- [ ] 28. Date picker — opens native picker? change triggers reload?
- [ ] 29-34. Range segment (日/周/月/季/年/自定义) — each triggers real `?days=N` reload?
- [ ] 35-38. Mode segment (自动/时/日/周) — visual toggle OR explicitly disabled?
- [ ] 39. 全量同步 button — triggers launchctl kickstart? toast says ~38s?
- [ ] 40. 重扫 button — clears cache + reloads?

### Brief view body

- [ ] 41. 活跃群 KPI — real number? subtext shows window?
- [ ] 42. 总消息 KPI — real from stats.json? subtext shows window-lock if different?
- [ ] 43. @ 我的 KPI — real from mentions.json? click → drawer?
- [ ] 44. 静默群 KPI — real?
- [ ] 45. 简报 (briefing) — real LLM output?
- [ ] 46. 复制摘要 button — clipboard.writeText? toast feedback?
- [ ] 47-52. Focus column 5-8 items — each has copy icon? click copies?
- [ ] 53-57. Actions column 3-5 items — each row click copies?
- [ ] 58-65. Sources column 8 items — render real cross-group senders?

### Other views

- [ ] 66. Live view — timeline sorted by time desc, real focus+actions merged?
- [ ] 67. Cross view — cross-group senders + by_type bar chart real?
- [ ] 68. Link view — truth mirror card with real ratios? URL list real? bar chart real?

### Drawers (6 types)

- [ ] 69. Mentions drawer — 4 windows + recent + by_group + by_sender all real?
- [ ] 70. Groups drawer — 100 groups with real names/unread/time?
- [ ] 71. Favorites drawer — 50 items from wx favorites?
- [ ] 72. Ungrouped drawer — math explained + button to all-groups?
- [ ] 73. Daemon drawer — real PID + binary path + status text?
- [ ] 74. Settings drawer — QUERY state + 4 file timestamps + backlog list?
- [ ] 75. × close button (in drawer) — closes?
- [ ] 76. Backdrop click — closes?
- [ ] 77. Esc key — closes?

## How to run the audit (5 minutes)

1. Open browser DevTools Console
2. Paste this:
```javascript
(function audit() {
  const interactives = document.querySelectorAll('[data-action], [data-view], [data-collection], [data-segment] .seg-btn, button, a[href], [onclick]');
  const rows = [...interactives].map(el => {
    const action = el.dataset?.action || el.dataset?.view || el.dataset?.collection || el.dataset?.val || (el.tagName === 'BUTTON' ? '(button)' : '(link)');
    const disabled = el.classList.contains('disabled') || el.hasAttribute('disabled');
    const tooltip = el.getAttribute('title') || '(no tooltip)';
    return { tag: el.tagName, action, disabled, tooltip: tooltip.slice(0, 40), text: (el.textContent || '').trim().slice(0, 20) };
  });
  console.table(rows);
  console.log(`Total: ${rows.length} · disabled: ${rows.filter(r => r.disabled).length}`);
})();
```
3. For each row, mentally classify: 🟢/🟡/🚫
4. Anything that's 🔴 DECORATIVE → fix it before shipping next feature

## Self-discipline rule

Before claiming "the dashboard is done", produce a public audit table with:
- N elements total
- X 🟢 REAL
- Y 🟡 HYBRID (each with documented limitation)
- Z 🚫 PLANNED (each visibly disabled)
- **0 🔴 DECORATIVE** (this is the gate)

If you can't say "0 decorative", you're not done.

## n=1 audit results (from the original build)

| Stage | 🟢 REAL | 🟡 HYBRID | 🔴 DECORATIVE | 🚫 PLANNED |
|---|---|---|---|---|
| Stage 4 (4-tabs added) | 33 (66%) | 7 (14%) | 13 (26%) | 2 (4%) |
| **Stage 8 (after audit-driven fix)** | **45 (90%)** | 0 | **0** | **5 (10%)** |

The Stage 4 → Stage 8 delta: 13 decorative buttons became 8 REAL + 5 explicitly PLANNED. No silent breakage. This is the bar.
