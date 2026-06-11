# UI 前端分离实现 Plan

- **关联 Design Doc**：[docs/specs/ui-separation-design.md](../specs/ui-separation-design.md)
- **关联 TASK**：TASK.md → P4
- **基线 commit**：`e3a84bb`（Step 3 scaffold）
- **目标**：把 `app/ui/live_frontend.py`（2256 行 React SPA 嵌入字符串）拆到 `app/static/`，分三步交付，Step 内按 Phase 或高风险检查点 commit，可逆。

---

## 0. 不变量（每个 Task 都必须遵守）

1. **className 一字符不改**：从 live_frontend.py 复制 JSX 到 .jsx 文件时，className 字符串不重写、不优化、不换行重排
2. **图表 title 字符串不改**：`findChart(charts, 'Installed Apps Category Share')` 等 title 字符串保持英文原文
3. **后端 API 不动**：`app/api/`、`app/services/`、`app/runtime_skills/`、`app/schemas/` 全部只读
4. **不安装依赖**：requirements.txt 不改；不创建 package.json
5. **CDN 版本锁定**：React 18.2.0 / ReactDOM 18.2.0 / lucide-react 0.292.0 / @babel/standalone / cdn.tailwindcss.com 与 live_frontend.py 一致
6. **每个 Phase 完成后 commit**（高风险检查点如 main.py 路由切换可单独 commit）；单个 Task 不强制 commit
7. **push 前 git remote -v**；只允许推送到当前批准仓库对应的 remote（当前默认 `origin`）
8. **找不到方法 / 看到歧义 → 停下问用户**
9. **允许修改 `app/main.py`**，仅限前端入口路由和 StaticFiles/FileResponse 相关逻辑；不得修改 API 路由和业务服务
10. **代码块中禁止使用 `...` 占位符**：如果 import 清单无法确定，写“按实际引用补齐”，不得在最终代码中保留 `...`
11. **本次 UI 分离只保持 live_frontend.py 当前已有渲染能力**，不新增 product_advice / ops_advice / standardized_labels 展示（当前未渲染）
12. **汇报节奏**：每个 Phase 完成后输出 `git diff --stat` + `git status`，commit 后停下汇报等用户确认；用户确认后再进入下一 Phase。单个 Task 内遇到歧义 / PoC 失败 / 视觉偏差 / import 失败时立即停下
13. **NS.b 命名空间约定（子选项 i）**：所有跨文件依赖通过 `window.AppUtils.<file>` / `window.AppServices.<file>` / `window.AppComponents.<Component>` 暴露与读取；不写 `import` / `export` / `from`；不写 `import React from 'react'`（React / ReactDOM / LucideReact 来自 UMD CDN，已是全局变量）；每个 .jsx 文件末尾必先 `window.AppX = window.AppX || {}` 再赋值
14. **index.html 标签顺序**：业务 `<script type="text/babel">` 必须按依赖拓扑顺序排（utils → services → common → charts → panels → 顶层 → app.jsx）；不加 `async` / `defer` / `data-type="module"`

---

## 1. 决策 4 子选项确认：i（React UMD + 多 `<script type="text/babel">` + window 全局）

> **历史记录**：原计划选 ii（importmap + esm.sh + 标准 import），Phase A PoC 实测失败 —— Babel Standalone 仅编译入口 `<script type="text/babel">` 内联 / src 内容，**不会递归编译通过 `import` 引用的 `.jsx` 子文件**，浏览器 ES module loader 拿到未编译的 JSX 源码直接报 SyntaxError。结论：子选项 ii 在 "无 Node toolchain" 约束下不可行，改用子选项 i。

**子选项 i 加载约定**：

- **CDN（UMD bundles）**：
  - React 18.2.0 UMD：`https://unpkg.com/react@18.2.0/umd/react.development.js` → 暴露 `window.React`
  - ReactDOM 18.2.0 UMD：`https://unpkg.com/react-dom@18.2.0/umd/react-dom.development.js` → 暴露 `window.ReactDOM`（`ReactDOM.createRoot` 替代 `react-dom/client`）
  - lucide-react 0.292.0 UMD：`https://unpkg.com/lucide-react@0.292.0/dist/umd/lucide-react.js` → 暴露 `window.LucideReact`
  - Tailwind Play CDN：`https://cdn.tailwindcss.com`
  - Babel Standalone：`https://unpkg.com/@babel/standalone/babel.min.js`
- **业务文件加载**：每个 `.jsx` 文件独立挂一个 `<script type="text/babel" src="/static/js/.../X.jsx">` 标签；index.html 中的标签按依赖拓扑顺序排列（utils → services → common → charts → panels → 顶层组件 → app.jsx）。
- **各 `.jsx` 文件不写 `import` / `export`**，改为：
  - 文件顶部从 `window` 读取依赖：例如 `const { useMemo, useState } = React;` / `const { Smartphone, Database } = LucideReact;` / `const { findChart } = window.AppUtils.chartLookup;`
  - 文件末尾把导出符号挂到对应命名空间。
- **NS.b 命名空间约定（已锁定）**：
  - `window.AppUtils.<file>` —— utils 层（`AppUtils.normalize` / `AppUtils.chartLookup` / `AppUtils.displayMappers` / `AppUtils.advice`）
  - `window.AppServices.<file>` —— services 层（`AppServices.api`）
  - `window.AppComponents.<Component>` —— 所有 React 组件（common / charts / panels / 顶层均扁平挂在此对象下，组件名为 PascalCase 键）
  - 每个文件在赋值前必须先 `window.AppX = window.AppX || {}` 防止覆盖
- **加载顺序保证**：浏览器对同一页面内多个 `<script>` 标签按出现顺序执行（无 `async` / `defer`）；Babel Standalone 对每个 `type="text/babel"` 标签是同步编译执行。所以只要 index.html 中按依赖顺序排标签，运行时即可保证 `window.App*` 在被读取前已被赋值。

**子选项 i 的取舍**：
- 优点：在无 Node toolchain 约束下唯一被 PoC 验证可行的方案；多 `<script>` 标签简单直观；无 importmap / esm.sh 外部依赖。
- 妥协：失去 ES module 静态依赖图（依赖关系靠 index.html 标签顺序维护）；命名空间靠约定而非语言强制；CDN 多了一个 lucide-react UMD 文件。
- 不进入考虑范围：编辑器内 `import` 自动补全 / 类型检查（项目本就无 TS / 无 Lint 配置）。

---

## 2. 步骤总览

| 提交 | 内容 | 默认行为 | fallback |
|---|---|---|---|
| Step-1 | `app/static/` 全部组件 + `app/main.py` 加 `?next=1` 分支 | 旧版 | 默认 `/` 保持旧版 fallback |
| Step-2 | 反转 `app/main.py` 默认 | 新版 | `?legacy=1` 旧版 |
| Step-3 | 删除 `app/ui/live_frontend.py` + `?legacy=1` 分支 | 新版 | 无 |

每步独立交付。Step-1 内部由 Phase A-H 共 24 个 Task 组成。Step-2 / Step-3 各 1 个 Task。总计 26 个 Task。

---

## 3. Step-1：新版上线但默认 off

### Phase A：冒烟验证多文件加载（PoC 已完成）

**结论（已实测）**：子选项 ii 失败，子选项 i.b + NS.b 通过。Phase A 已结束，不再产生新 Task。

**PoC 历史**：
1. **首次尝试（子选项 ii）**：`app.jsx` 用 `import { Hello } from './components/Hello.jsx'` 引用子组件，index.html 用 `<script type="text/babel" data-type="module" src="/static/js/app.jsx">`。结果：浏览器报 `Unexpected token '<'`，根因为 Babel Standalone 仅编译入口 src 文件，不递归编译被 `import` 的子 `.jsx`，浏览器 ES module loader 拿到未经编译的 JSX 直接 SyntaxError。
2. **切换到子选项 i.b + NS.b**：
   - index.html 引入 React UMD / ReactDOM UMD / lucide-react UMD / Babel Standalone / Tailwind Play CDN；
   - `Hello.jsx` 用 `function Hello(...)` 定义后 `window.AppComponents.Hello = Hello;`；
   - `app.jsx` 用 `const { Hello } = window.AppComponents;` 读取，再 `ReactDOM.createRoot(...).render(<Hello .../>);`；
   - index.html 按 `Hello.jsx` → `app.jsx` 顺序排两个 `<script type="text/babel" src="...">`。
3. **PoC 结果**：浏览器渲染 "Hello, Step 4 PoC i.b/NS.b!" 成功，Console 无报错。

**清理状态**（已执行）：
- 删除 `app/static/js/components/Hello.jsx`
- `app/static/js/app.jsx` 还原为 Step 3 stub（`console.log("app loaded")`）
- `app/static/index.html` 保留子选项 i 形态（React UMD + Babel + 不带 importmap / esm.sh），作为后续 Phase B-H 的入口骨架

**单独 commit**：`chore(ui): switch from sub-option ii (ESM) to i (UMD+globals) after PoC`（记录子选项切换 + 清理 PoC 文件）。Phase A 不再产生进一步 commit。

---

### Phase B：utils 层（4 个 Task）

utils 是叶子层，无内部 import，最先拆。

#### Task B.1 — `utils/normalize.js`

**目的**：搬运 normalize 类工具函数（无业务依赖，纯 JS）。

**搬运清单**（live_frontend.py 行号）：
- `normalizeAnalysisResult` (1772)
- `normalizeAgentOutput` (1782)
- `buildEmptyAgentOutput` (1792)
- `normalizeApplicationTime` (1801)
- `objectValue` (1819)
- `arrayValue` (1823)
- `stringValue` (1827)
- `numberValue` (1831)
- `parsePercent` (1842)

**操作**：
1. 创建 `app/static/js/utils/normalize.js`
2. 从 live_frontend.py 上述行号原样复制函数体（不改逻辑、不改空格）
3. 文件头加 `// Extracted from app/ui/live_frontend.py during UI separation Step-1.`
4. **不写 `export`**；文件末尾追加：
   ```js
   window.AppUtils = window.AppUtils || {};
   window.AppUtils.normalize = {
     normalizeAnalysisResult,
     normalizeAgentOutput,
     buildEmptyAgentOutput,
     normalizeApplicationTime,
     objectValue,
     arrayValue,
     stringValue,
     numberValue,
     parsePercent,
   };
   ```

**验证命令**：
```bash
python -c "
import re
src = open('app/ui/live_frontend.py', encoding='utf-8').read()
dst = open('app/static/js/utils/normalize.js', encoding='utf-8').read()
for name in ['normalizeAnalysisResult','normalizeAgentOutput','buildEmptyAgentOutput','normalizeApplicationTime','objectValue','arrayValue','stringValue','numberValue','parsePercent']:
    assert name in dst, f'missing {name}'
    print(f'OK: {name}')
"
```

**通过条件**：脚本输出 9 个 OK，无 AssertionError。

**变更摘要**：`feat(ui): extract utils/normalize.js from live_frontend.py`

#### Task B.2 — `utils/chartLookup.js`

**搬运清单**（源：live_frontend.py L1978-L2055）：
- `findChart` (1978)
- `chartSeriesData` (1982)
- `chartValue` (1987)
- `chartMetaLevels` (1992)
- `buildConicGradient` (1996)
- `findPrimaryCategoryIndex` (2029)
- `polarToCartesian` (2035)
- `donutSegmentPath` (2043)

**操作**：与 B.1 同。**不写 `export`**；文件末尾追加：
```js
window.AppUtils = window.AppUtils || {};
window.AppUtils.chartLookup = {
  findChart, chartSeriesData, chartValue, chartMetaLevels,
  buildConicGradient, findPrimaryCategoryIndex, polarToCartesian, donutSegmentPath,
};
```

**验证命令**：
```bash
python -c "
src = open('app/ui/live_frontend.py', encoding='utf-8').read()
dst = open('app/static/js/utils/chartLookup.js', encoding='utf-8').read()
for name in ['findChart','chartSeriesData','chartValue','chartMetaLevels','buildConicGradient','findPrimaryCategoryIndex','polarToCartesian','donutSegmentPath']:
    assert name in dst, f'missing {name}'
    print(f'OK: {name}')
"
```

**变更摘要**：`feat(ui): extract utils/chartLookup.js from live_frontend.py`

#### Task B.3 — `utils/displayMappers.js`

**搬运清单**（源：live_frontend.py L1848-L1970 + L2018 + L2059-L2241，formatter / 显示文本映射）：
- `formatCurrencyMxn` (1848) / `formatCurrency` (2133)
- `formatCreditConfidence` (1852) / `formatCreditLevel` (1865) / `formatCreditSourceName` (1881)
- `formatCreditRiskFlag` (1889) / `formatCreditTag` (1906) / `formatCreditStatus` (1937)
- `formatCreditUtilizationInsight` (1949) / `normalizeCreditAccountType` (1963)
- `riskBadgeClass` (2138) / `toRiskLabel` (2148)
- `toFinancialDisplayLabel` (2157) / `toConsumptionDisplayLabel` (2166)
- `toSegmentDisplay` (2176) / `toSegmentFeature` (2188)
- `toValueSignalDisplay` (2200) / `toConfidenceDisplay` (2209) / `toRiskDisplay` (2218)
- `formatInlineList` (2069)
- `tokenToBgClass` (2074) / `colorByIndex` (2059) / `softTagToneClass` (2064)
- `levelWidthClass` (2102) / `scoreBandWidthClass` (2114) / `repaymentWidthClass` (2124)
- `normalizeMetricKey` (2018)

**操作**：与 B.1 同。**不写 `export`**；文件末尾把上述全部函数挂到 `window.AppUtils.displayMappers = { ... }`（按实际函数名补齐，禁止占位符）。

**验证命令**：
```bash
python -c "
dst = open('app/static/js/utils/displayMappers.js', encoding='utf-8').read()
for name in ['formatCurrencyMxn','formatCreditConfidence','formatCreditLevel','formatCreditSourceName','formatCreditRiskFlag','formatCreditTag','formatCreditStatus','formatCreditUtilizationInsight','normalizeCreditAccountType','formatCurrency','formatInlineList','tokenToBgClass','colorByIndex','softTagToneClass','levelWidthClass','scoreBandWidthClass','repaymentWidthClass','normalizeMetricKey','riskBadgeClass','toRiskLabel','toFinancialDisplayLabel','toConsumptionDisplayLabel','toSegmentDisplay','toSegmentFeature','toValueSignalDisplay','toConfidenceDisplay','toRiskDisplay']:
    assert name in dst, f'missing {name}'
    print(f'OK: {name}')
"
```

**变更摘要**：`feat(ui): extract utils/displayMappers.js from live_frontend.py`

#### Task B.4 — `utils/advice.js`

**搬运清单**（源：live_frontend.py L2227-L2256）：
- `buildComprehensiveMarketingSuggestion` (2227)
- `buildComprehensiveRiskSuggestion` (2241)

**操作**：与 B.1 同。**不写 `export`**；文件末尾追加：
```js
window.AppUtils = window.AppUtils || {};
window.AppUtils.advice = {
  buildComprehensiveMarketingSuggestion,
  buildComprehensiveRiskSuggestion,
};
```

**变更摘要**：`feat(ui): extract utils/advice.js from live_frontend.py`

**Phase B commit**：`feat(ui): extract utility modules (normalize/chartLookup/displayMappers/advice)`

---

### Phase C：services 层（1 个 Task）

#### Task C.1 — `services/api.js`

**目的**：把 `requestByUid` / `requestByFile`（live_frontend.py:78-113）抽到独立文件，作为唯一接触 fetch 的位置。

**操作**：
创建 `app/static/js/services/api.js`：

```js
// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// All fetch calls live here so future SSE / polling switches are local to this file.

async function analyzeByUid(trimmedUid, normalizedApplicationTime) {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      uid: trimmedUid,
      application_time: normalizedApplicationTime
    })
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || '分析请求失败，请稍后重试。');
  }

  return payload;
}

async function analyzeByFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/analyze-file', {
    method: 'POST',
    body: formData
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || '文件分析请求失败，请检查文件内容。');
  }

  return payload;
}

window.AppServices = window.AppServices || {};
window.AppServices.api = { analyzeByUid, analyzeByFile };
```

**验证命令**：
```bash
grep -c "fetch(" app/static/js/services/api.js
# 期望：2
```

**变更摘要**：`feat(ui): extract services/api.js from live_frontend.py`

**Phase C commit**：`feat(ui): extract services/api.js`

---

### Phase D：common 子组件（5 个 Task）

无业务依赖、被 panels 复用的小组件。

#### Task D.1 — `components/common/InfoRow.jsx` + `ProgressRow.jsx` + `CreditProgressRow.jsx` + `LegendDot.jsx`

**搬运清单**（live_frontend.py 行号）：
- `InfoRow` (1627) — props: `{label, value, valueClass}`
- `ProgressRow` (1636) — props: `{label, value, widthClass, barClass}`
- `CreditProgressRow` (1645) — props: `{label, levelLabel, value, widthPercent, barClass, note, levelClass}`
- `LegendDot` (1664) — props: `{color, label}`

**操作**：
1. 创建 4 个文件 `app/static/js/components/common/{InfoRow,ProgressRow,CreditProgressRow,LegendDot}.jsx`
2. 每个文件**不写 `import React`**；如需 React hooks，在文件顶部加 `const { useState, useMemo } = React;`（只取本文件实际用到的 hook）
3. 函数定义不加 `export`
4. JSX 原样复制
5. 文件末尾追加：
   ```jsx
   window.AppComponents = window.AppComponents || {};
   window.AppComponents.InfoRow = InfoRow;  // 或对应组件名
   ```

**验证**：grep 4 个组件名 + `window.AppComponents.<Name>` 出现在对应文件。

**变更摘要**：`feat(ui): extract common row components (Info/Progress/CreditProgress/LegendDot)`

#### Task D.2 — `components/common/MarkdownBlock.jsx`

**搬运清单**（源：live_frontend.py L1602-L1625 + L1809-L1818）：
- `MarkdownBlock` (1602) — props: `{text}`
- 同时把 `renderInlineMarkdown` (1809) 一并搬到此文件（仅被 MarkdownBlock 使用）

**操作**：
1. 创建 `app/static/js/components/common/MarkdownBlock.jsx`
2. **不写 `import React`**；如需 hook 在文件顶部 `const { ... } = React;`
3. `renderInlineMarkdown` 不挂到 window（文件内部使用）
4. 文件末尾：`window.AppComponents = window.AppComponents || {}; window.AppComponents.MarkdownBlock = MarkdownBlock;`

**变更摘要**：`feat(ui): extract common/MarkdownBlock.jsx`

#### Task D.3 — `components/common/MetricHelpTip.jsx`

**搬运清单**（源：live_frontend.py L1696-L1726）：
- `MetricHelpTip` (1696) — props: `{explanation, isOpen, onMouseEnter, onMouseLeave, onToggle}`

**操作**：与 D.1 同。

**变更摘要**：`feat(ui): extract common/MetricHelpTip.jsx`

#### Task D.4 — `components/common/InstallBucketModal.jsx` + `CategoryAppsModal.jsx`

**搬运清单**（源：live_frontend.py L1727-L1753）：
- `InstallBucketModal` (1727) — props: `{bucket, groups, onClose}`
- `CategoryAppsModal` (1739) — props: `{category, detail, onClose, open}`

**变更摘要**：`feat(ui): extract common modal components (InstallBucket/CategoryApps)`

#### Task D.5 — `components/common/TimelineItem.jsx`

**搬运清单**（源：live_frontend.py L1754-L1770）：
- `TimelineItem` (1754) — props: `{time, title, sub, icon: Icon, color, isLast}`

**注意**：props 解构使用 `icon: Icon`（重命名）—— Icon 是组件，由父组件从 lucide-react 传入。

**变更摘要**：`feat(ui): extract common/TimelineItem.jsx`

**Phase D commit**：`feat(ui): extract common components`

---

### Phase E：charts 组件（3 个 Task）

#### Task E.1 — `components/charts/DonutChart.jsx`

**搬运清单**：
- `InteractiveDonutChart` (1673) — props: `{items, palette, activeIndex, onHover, onLeave, onSelect, size}`

**依赖**：`donutSegmentPath` / `polarToCartesian` / `colorByIndex` / `findPrimaryCategoryIndex`（来自 utils/chartLookup.js + utils/displayMappers.js）

**操作**：
1. 创建 `app/static/js/components/charts/DonutChart.jsx`
2. 文件顶部依赖读取：
   ```jsx
   const { donutSegmentPath, polarToCartesian, findPrimaryCategoryIndex } = window.AppUtils.chartLookup;
   const { colorByIndex } = window.AppUtils.displayMappers;
   // 如需 React hooks：const { useState, useMemo } = React;（按本文件实际使用补齐）
   ```
3. `function InteractiveDonutChart({ items, palette, activeIndex, onHover, onLeave, onSelect, size })`——props 按 live_frontend.py 原定义完整复制，**不加 `export`**
4. 文件末尾：`window.AppComponents = window.AppComponents || {}; window.AppComponents.InteractiveDonutChart = InteractiveDonutChart;`

**验证**：
```bash
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8000/static/js/components/charts/DonutChart.jsx
# 期望：200（静态文件可达）
```
浏览器 import 验证放到 Phase G/H 整体测试。

**变更摘要**：`feat(ui): extract charts/DonutChart.jsx (InteractiveDonutChart)`

#### Task E.2 — `components/charts/CreditGauge.jsx`

**搬运清单**：从 RichCreditPanel（1254）内 `<svg width="100%" height="100%" viewBox="0 0 320 180">`（行 1374）整段半圆 gauge SVG 抽出。

**操作**：
1. 创建 `app/static/js/components/charts/CreditGauge.jsx`
2. 把 SVG 段落连同其状态依赖封装成组件
3. **props 接口（已锁定）**：`{scoreValue}`
   - `scoreValue`：gauge 填充百分比 + 文本显示值（来自 RichCreditPanel 的 `scoreValue` 局部变量）
4. 在 RichCreditPanel 内的对应位置后续会被替换为 `<CreditGauge scoreValue={scoreValue} />`（在 Task F.4 中执行）

**注意**：本 Task **只创建组件文件**，不动 RichCreditPanel 内联 SVG。RichCreditPanel 在 F.4 整体搬运时会同步替换为组件调用。

**风险**：gauge SVG 包含若干 inline 计算（如指针角度）。如果发现某些计算依赖 RichCreditPanel 的其他局部状态而非清单里的 props，**停下问用户**，不要自行扩展 props。

**命名空间挂载**：文件末尾 `window.AppComponents = window.AppComponents || {}; window.AppComponents.CreditGauge = CreditGauge;`

**变更摘要**：`feat(ui): extract charts/CreditGauge.jsx`

#### Task E.3 — `components/charts/CreditRiskStructure.jsx`

**搬运清单**：从 RichCreditPanel（1254）内 `<svg width="320" height="280" viewBox="0 0 320 280">`（行 1571）整段抽出。

**操作**：与 E.2 同。

**props 接口（已锁定）**：`{radarDimensions, radarValues, radarPolygon, centerX, centerY}`
- `radarDimensions`：维度标签数组（{label, value} 对象列表）
- `radarValues`：归一化分数数组（0-100）
- `radarPolygon`：预计算的多边形点坐标字符串
- `centerX`/`centerY`：中心坐标（固定值 150/135）

**注意**：`radarPoint(value, index, count)` 函数保留在 RichCreditPanel.jsx 内部用于预计算 `radarPolygon`。CreditRiskStructure.jsx 只消费传入的 props，不再声明 `radarPoint`。

**命名空间挂载**：文件末尾 `window.AppComponents = window.AppComponents || {}; window.AppComponents.CreditRiskStructure = CreditRiskStructure;`

**变更摘要**：`feat(ui): extract charts/CreditRiskStructure.jsx`

**Phase E commit**：`feat(ui): extract chart components (DonutChart/CreditGauge/CreditRiskStructure)`

---

### Phase F：panels（5 个 Task）

#### Task F.1 — `components/panels/AppPanel.jsx`

**搬运清单**：
- `AppPanel` (665) — props: `{profile}`
- 内部状态：`hoveredCategoryIndex` / `pinnedCategoryIndex` / `installBucketState` / `categoryAppsState`
- 内部 helper：`activeCategoryIndex` 计算等（在 AppPanel 内部定义的局部变量保留在文件内）

**操作**：
1. 创建 `app/static/js/components/panels/AppPanel.jsx`
2. 文件顶部依赖读取（**不写 `import`**）：
   ```jsx
   const { useMemo, useState } = React;
   const { PieChart, Smartphone, Database, TrendingUp, BrainCircuit } = LucideReact;
   const { arrayValue, objectValue, stringValue, numberValue } = window.AppUtils.normalize;
   const { findChart, chartSeriesData } = window.AppUtils.chartLookup;
   const { tokenToBgClass, colorByIndex, levelWidthClass } = window.AppUtils.displayMappers;
   // 以上为示例，按实际引用补齐全部符号，禁止保留占位符
   const {
     InteractiveDonutChart,
     ProgressRow,
     LegendDot,
     InstallBucketModal,
     CategoryAppsModal,
     MetricHelpTip,
     MarkdownBlock,
   } = window.AppComponents;
   ```
3. JSX 原样搬运
4. `function AppPanel({ profile })` —— props 按 live_frontend.py 原定义完整复制，**不加 `export`**
5. 文件末尾：`window.AppComponents = window.AppComponents || {}; window.AppComponents.AppPanel = AppPanel;`

**lucide-react 图标清单（已预列）**：
- AppPanel：`Smartphone`, `Database`, `TrendingUp`, `PieChart`, `BrainCircuit`
- BehaviorPanel：`Activity`, `Calendar`, `MessageSquare`
- CreditPanel：`CreditCard`
- RichCreditPanel：`CreditCard`
- ComprehensivePanel：`Network`, `ShieldCheck`, `Target`, `UserCheck`, `Calendar`
- HomeView：`BrainCircuit`, `Bot`, `Search`, `FileUp`, `AlertCircle`
- DashboardView：`ChevronRight`, `Bot`, `Network`, `Smartphone`, `Activity`, `CreditCard`

import 时按上述清单按需引入，不全量 import 整个 LucideReact。**实际写法**：每个 panel 文件顶部 `const { Icon1, Icon2, ... } = LucideReact;`（按本 panel 实际使用的图标列出，不要一次性列全部）。

**验证命令**（搬运后）：
```bash
# 确认所有 className 字符串与原文件对齐（采样校验）
python -c "
src = open('app/ui/live_frontend.py', encoding='utf-8').read()
dst = open('app/static/js/components/panels/AppPanel.jsx', encoding='utf-8').read()
# 选 3 个标志性 className 字符串
for cls in ['rounded-2xl shadow-sm border border-slate-200', 'flex items-center gap-2', 'text-base font-bold text-slate-800']:
    assert cls in dst, f'missing className: {cls!r}'
    print('OK:', cls)
"
```

**变更摘要**：`feat(ui): extract panels/AppPanel.jsx`

#### Task F.2 — `components/panels/BehaviorPanel.jsx`

**搬运清单**：
- `BehaviorPanel` (766) — props: `{profile}`
- 内部 helper：`normalizeTimeLabel` (844) / `compactEventCount` (849) / `rawEventCount` (855) / `scrollToSection` (861)
  - 这些是 BehaviorPanel 闭包内函数，**保留在 BehaviorPanel.jsx 内部**，不抽到 utils

**操作**：与 F.1 同。

**变更摘要**：`feat(ui): extract panels/BehaviorPanel.jsx`

#### Task F.3 — `components/panels/CreditPanel.jsx`

**搬运清单**：
- `CreditPanel` (1209) — props: `{profile}`
- **注意**：原文件 1209 行有缩进异常（顶层定义而非嵌套），搬运时**保持缩进异常的语义不动**——但 .jsx 顶层函数定义本来就是顶层缩进，所以这是搬到新文件后的自然形态。**不视为代码改动**。

**操作**：与 F.1 同。

**变更摘要**：`feat(ui): extract panels/CreditPanel.jsx`

#### Task F.4 — `components/panels/RichCreditPanel.jsx`

**搬运清单**：
- `RichCreditPanel` (1254) — props: `{profile}`
- 内部 helper：`radarPoint` (1320) — 保留在 RichCreditPanel.jsx 内部
- **替换内联 SVG**：把 1374 处 inline `<svg>` 替换为 `<CreditGauge scoreValue={scoreValue} />`；把 1571 处替换为 `<CreditRiskStructure radarDimensions={radarDimensions} radarValues={radarValues} radarPolygon={radarPolygon} centerX={centerX} centerY={centerY} />`

**操作**：
1. 与 F.1 同先做组件文件
2. 在文件顶部依赖读取处加上 `const { CreditGauge, CreditRiskStructure } = window.AppComponents;`（与其他 `window.AppComponents` 解构合并到一处）
3. 替换 inline SVG 为 `<CreditGauge scoreValue={scoreValue} />` 和 `<CreditRiskStructure radarDimensions={radarDimensions} radarValues={radarValues} radarPolygon={radarPolygon} centerX={centerX} centerY={centerY} />`，保持周围容器 div / className 不动
4. 文件末尾：`window.AppComponents.RichCreditPanel = RichCreditPanel;`

**风险**：如果替换组件后视觉与原版有偏差（如 SVG 容器 className 漏迁），**停下问用户**，不要自行调整尺寸 / 颜色。

**变更摘要**：`feat(ui): extract panels/RichCreditPanel.jsx + wire charts subcomponents`

#### Task F.5 — `components/panels/ComprehensivePanel.jsx`

**搬运清单**：
- `ComprehensivePanel` (440) — props: `{profile}`

**操作**：与 F.1 同。

**变更摘要**：`feat(ui): extract panels/ComprehensivePanel.jsx`

**Phase F commit**：`feat(ui): extract panel components (App/Behavior/Credit/RichCredit/Comprehensive)`

---

### Phase G：顶层组件 + 入口（3 个 Task）

#### Task G.1 — `components/HomeView.jsx` + `LoadingView.jsx`

**搬运清单**：
- `HomeView` (206) — props: `{uid, setUid, uidError, setUidError, applicationTime, setApplicationTime, selectedFile, setSelectedFile, onStartUid, onStartFile, errorMessage}`
- `LoadingView` (333) — props: `{text}`

**变更摘要**：`feat(ui): extract Home/LoadingView components`

#### Task G.2 — `components/DashboardView.jsx`

**搬运清单**（源：live_frontend.py L349-L438）：
- `DashboardView` (349) — **props（已锁定，共 6 个）**：
  `{activeTab, setActiveTab, analysisResults, selectedResultIndex, setSelectedResultIndex, onBack}`

**操作**：
1. 创建 `app/static/js/components/DashboardView.jsx`
2. 文件顶部依赖读取（**不写 `import`**）：
   ```jsx
   const { ChevronRight, Bot, Network, Smartphone, Activity, CreditCard } = LucideReact;
   const {
     AppPanel,
     BehaviorPanel,
     CreditPanel,
     RichCreditPanel,
     ComprehensivePanel,
   } = window.AppComponents;
   // 如需 React hooks：const { useState } = React;（按实际使用补齐）
   ```
3. JSX 原样搬运
4. `function DashboardView({ activeTab, setActiveTab, analysisResults, selectedResultIndex, setSelectedResultIndex, onBack })`——完整 props 列表，禁止保留占位符，**不加 `export`**
5. 文件末尾：`window.AppComponents = window.AppComponents || {}; window.AppComponents.DashboardView = DashboardView;`

**变更摘要**：`feat(ui): extract DashboardView.jsx + wire 5 panel components`

#### Task G.3 — `app.jsx` 顶层组装 + index.html 切到新版入口

**操作**：

1. 改写 `app/static/js/app.jsx`：把 live_frontend.py 的 `function App()`（49-204 行）整段搬过来，按实际逻辑完整复制，禁止保留占位符
   ```jsx
   const { useState } = React;
   const { HomeView, LoadingView, DashboardView } = window.AppComponents;
   const { normalizeAnalysisResult, buildEmptyAgentOutput, normalizeApplicationTime } = window.AppUtils.normalize;
   const { analyzeByUid, analyzeByFile } = window.AppServices.api;

   const UID_PATTERN = /^\d{18}$/;

   const FALLBACK_RESULT = {
     uid: '',
     app_profile: buildEmptyAgentOutput('暂无 App 画像结果'),
     behavior_profile: buildEmptyAgentOutput('暂无行为画像结果'),
     credit_profile: buildEmptyAgentOutput('暂无征信画像结果'),
     comprehensive_profile: buildEmptyAgentOutput('暂无综合画像结果')
   };

   const LOADING_TEXTS = [
     '正在唤醒多智能体系统...',
     'App画像Agent：正在提取安装列表与分类标签...',
     '行为画像Agent：正在分析埋点行为与活跃度...',
     '征信画像Agent：正在解析征信报告与风险结果...',
     '综合画像Agent：正在进行三维整合推理...'
   ];

   // App 函数体：必须从 live_frontend.py L49-L204 完整搬运。
   // 禁止提交空 App 或注释占位 App。
   // 搬运时将 requestByUid 调用替换为 analyzeByUid，requestByFile 替换为 analyzeByFile。

   const root = ReactDOM.createRoot(document.getElementById('root'));
   root.render(<App />);
   ```

   > **注意**：上面代码块中 `function App()` 的函数体未展示——执行时必须从 live_frontend.py L49-L204 完整复制，不允许保留注释占位。如果函数体超过 150 行，正常（原文就是这么长）。

2. **关键改动 1**：原 live_frontend.py 中 `requestByUid` / `requestByFile` 是 App 内闭包，搬运时**移除这两个内嵌函数定义**，把 `handleAnalyze` 中的调用改为 `analyzeByUid(...)` / `analyzeByFile(...)`。**这是 services 层封装的唯一行为变化**。

3. **关键改动 2**：原 live_frontend.py 中 `UID_PATTERN = /^\\d{18}$/` 是 Python 字符串里的双反斜杠，**搬到 .jsx 文件后改为 `/^\d{18}$/` 单反斜杠**——这是字符串脱嵌套的修正，不是逻辑改动。

4. 改写 `app/static/index.html`：把所有业务文件按依赖拓扑顺序追加为 `<script type="text/babel" src="/static/js/.../X.jsx"></script>`：
   ```html
   <!-- utils 层（叶子，无依赖） -->
   <script type="text/babel" src="/static/js/utils/normalize.js"></script>
   <script type="text/babel" src="/static/js/utils/chartLookup.js"></script>
   <script type="text/babel" src="/static/js/utils/displayMappers.js"></script>
   <script type="text/babel" src="/static/js/utils/advice.js"></script>
   <!-- services 层 -->
   <script type="text/babel" src="/static/js/services/api.js"></script>
   <!-- common 子组件 -->
   <script type="text/babel" src="/static/js/components/common/InfoRow.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/ProgressRow.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/CreditProgressRow.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/LegendDot.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/MarkdownBlock.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/MetricHelpTip.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/InstallBucketModal.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/CategoryAppsModal.jsx"></script>
   <script type="text/babel" src="/static/js/components/common/TimelineItem.jsx"></script>
   <!-- charts 子组件 -->
   <script type="text/babel" src="/static/js/components/charts/DonutChart.jsx"></script>
   <script type="text/babel" src="/static/js/components/charts/CreditGauge.jsx"></script>
   <script type="text/babel" src="/static/js/components/charts/CreditRiskStructure.jsx"></script>
   <!-- panels（依赖 common + charts + utils） -->
   <script type="text/babel" src="/static/js/components/panels/AppPanel.jsx"></script>
   <script type="text/babel" src="/static/js/components/panels/BehaviorPanel.jsx"></script>
   <script type="text/babel" src="/static/js/components/panels/CreditPanel.jsx"></script>
   <script type="text/babel" src="/static/js/components/panels/RichCreditPanel.jsx"></script>
   <script type="text/babel" src="/static/js/components/panels/ComprehensivePanel.jsx"></script>
   <!-- 顶层视图 -->
   <script type="text/babel" src="/static/js/components/HomeView.jsx"></script>
   <script type="text/babel" src="/static/js/components/LoadingView.jsx"></script>
   <script type="text/babel" src="/static/js/components/DashboardView.jsx"></script>
   <!-- 入口 -->
   <script type="text/babel" src="/static/js/app.jsx"></script>
   ```
   - 浏览器对同一页面 `<script>` 标签按出现顺序同步执行（无 `async` / `defer`），所以上述顺序保证 `window.App*` 在被读取前已被赋值
   - **保留 Step 3 已有的 React UMD / ReactDOM UMD / lucide-react UMD / Babel Standalone / Tailwind Play CDN `<script>` 标签**，仅在 `<body>` 内追加业务文件 `<script type="text/babel">` 标签

**验证命令**：
```bash
# 确认 app.jsx 已经不是 stub
grep -c "createRoot" app/static/js/app.jsx
# 期望：1

# 确认所有组件能被静态服务返回 200
for f in /static/index.html /static/js/app.jsx /static/js/components/HomeView.jsx /static/js/components/DashboardView.jsx /static/js/components/panels/AppPanel.jsx; do
  curl -sf -o /dev/null -w "%{http_code} $f\n" http://localhost:8000$f
done
# 期望：每行都是 200
```

**变更摘要**：`feat(ui): wire app.jsx top-level App + UID pattern de-escape`

**G.3 防占位验证**（提交前必跑）：
```bash
# 确认 App 函数定义存在
grep -c "function App" app/static/js/app.jsx
# 期望：1

# 确认无注释占位残留
grep -c "函数体未展示\|完整搬运\|禁止提交空 App" app/static/js/app.jsx
# 期望：0
```

---

### Phase H：main.py 加 ?next=1 分支（1 个 Task）

#### Task H.1 — `app/main.py` `GET /` 加 `?next=1` 分支

**操作**：

修改 `app/main.py` 的 `homepage()` 函数：

```python
from fastapi import Request

@app.get("/", response_class=HTMLResponse, summary="Homepage")
def homepage(request: Request):
    """Serve the homepage. ?next=1 returns the new app/static/index.html."""
    if request.query_params.get("next") == "1":
        return FileResponse(STATIC_DIR / "index.html")
    return HTMLResponse(LIVE_FRONTEND_HTML)
```

import 调整：
- 已有 `from fastapi import FastAPI` → 改为 `from fastapi import FastAPI, Request`
- 已有 `from fastapi.responses import HTMLResponse` / `from fastapi.responses import JSONResponse` → 加 `from fastapi.responses import FileResponse`

**验证命令**（uvicorn 已运行）：
```bash
# 默认仍是旧版
curl -s http://localhost:8000/ | grep -c "react.development.js"
# 期望：1（旧版用 unpkg 拉 react.development）

# ?next=1 拿到新版
curl -s "http://localhost:8000/?next=1" | grep -c '/static/js/app.jsx'
# 期望：1（新版 index.html 含 app.jsx 业务入口标签）

# /static 仍可达
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8000/static/index.html
# 期望：200
```

**浏览器验证**：
- `http://localhost:8000/` → 旧版（与 Step 3 之前完全一致）
- `http://localhost:8000/?next=1` → 新版，开两 tab 逐 panel 视觉对比（重点：donut hover/pin、credit gauge、Modal、timeline、Markdown）

**通过条件**：新版 4 个 tab / 5 个 panel 组件视觉与旧版一致；DevTools Console 无 SyntaxError / `React is not defined` / `LucideReact is not defined` / `Cannot read properties of undefined`（NS.b 路径错误）；hover/pin/Modal 交互正常。

**变更摘要**：`feat(ui): add ?next=1 branch in GET / for new frontend [Step-1 complete]`

**Phase G-H commit**：`feat(ui): wire app.jsx + add ?next=1 route [Step-1 complete]`

---

### Step-1 收尾

Step-1 完成后整体 push（git remote -v 确认）：

```bash
git remote -v
# 必须看到 origin → lizheng33193/CHORD（或其他已确认指向当前项目的 GitHub remote）
git push origin main
```

**Phase 级 push 策略**：每完成一个 Phase（如 Phase B 全部 4 个 Task commit 后），可选执行 `git push origin main` 作为进度保存点，避免中间断开对话导致本地 commit 丢失风险。

**Step-1 退出条件**：
- Phase A PoC 已验证并清理（工作区回到 stub 状态）
- Phase B-H 已按 Phase 或高风险检查点完成 commit
- `curl http://localhost:8000/` 返回旧版
- `curl http://localhost:8000/?next=1` 返回新版
- 新版 4 个 tab / 5 个 panel 组件（AppPanel / BehaviorPanel / CreditPanel / RichCreditPanel / ComprehensivePanel）视觉与旧版一致（你的人工对比通过）
- DevTools Console 无 SyntaxError / `React is not defined` / `LucideReact is not defined` / `Cannot read properties of undefined`（NS.b 路径错误）/ MIME type error
- `python -m pytest tests/ -q --tb=short` 全过（确认 main.py 改动未影响后端）
- Chart title 字符串保留校验：
  ```bash
  python -c "
  from pathlib import Path
  src = Path('app/ui/live_frontend.py').read_text(encoding='utf-8')
  new = '\\n'.join(p.read_text(encoding='utf-8') for p in Path('app/static/js').rglob('*.*'))
  for title in ['Installed Apps Category Share','Credit Risk Level','Credit Risk Structure']:
      assert title in src, f'missing in source: {title}'
      assert title in new, f'missing in new frontend: {title}'
  print('OK: chart titles preserved')
  "
  ```

---

## 4. Step-2：切换默认为新版

### Task Step-2.1 — 反转 `app/main.py` 默认分支

**触发条件**：用户确认 Step-1 部署后稳定，没有发现需要立即修复的回归。

**操作**：

```python
@app.get("/", response_class=HTMLResponse, summary="Homepage")
def homepage(request: Request):
    """Serve the homepage. ?legacy=1 returns the old live_frontend.py for fallback."""
    if request.query_params.get("legacy") == "1":
        return HTMLResponse(LIVE_FRONTEND_HTML)
    return FileResponse(STATIC_DIR / "index.html")
```

**验证命令**：
```bash
# 默认是新版
curl -s http://localhost:8000/ | grep -c '/static/js/app.jsx'
# 期望：1

# ?legacy=1 仍是旧版
curl -s "http://localhost:8000/?legacy=1" | grep -c "react.development.js"
# 期望：1
```

**浏览器验证**：
- `http://localhost:8000/` → 新版
- `http://localhost:8000/?legacy=1` → 旧版（应急 fallback 仍可达）
- （可选，需用户单独确认）端到端真实 LLM 流程（vertex 模式，1 个真实 UID）跑通无回归。默认不自动调用真实 LLM，此项不作为强制退出条件

**变更摘要**：`refactor(ui): switch GET / default to new app/static/ frontend`

**push**：`git push origin main`

**Step-2 退出条件**：
- 默认访问拿到新版
- `?legacy=1` 仍可访问旧版
- 没有需要 revert 的回归
- （可选，需用户单独确认）端到端真实 LLM e2e 跑通。默认不要求

---

## 5. Step-3：删除 live_frontend.py

### Task Step-3.1 — 删除旧版 + 移除 ?legacy=1 分支

**触发条件**：用户确认"新版稳定"——不设固定天数，由用户判断。

**操作**：

1. 删除文件：`git rm app/ui/live_frontend.py`

2. 改写 `app/main.py`：
   - 移除 `from app.ui.live_frontend import LIVE_FRONTEND_HTML`
   - 移除 `from fastapi.responses import HTMLResponse`（若不再使用——验证 grep）
   - `homepage()` 简化为：
     ```python
     @app.get("/", summary="Homepage")
     def homepage():
         """Serve the new frontend index.html."""
         return FileResponse(STATIC_DIR / "index.html")
     ```
   - 移除 `Request` import（若不再使用）

3. 更新 PLANNING.md：把 `live_frontend.py 🔲 待分离到 app/static/` 行整体删除；更新记录加一条 [2026-04-XX] UI 前端分离 Step-3 完成

4. 更新 TASK.md：P4 从 `[ ]` 改为 `[x]`；"开发中发现"里的 live_frontend.py 条目从 `[ ]` 改为 `[x]`

**验证命令**：
```bash
# live_frontend.py 不存在
test ! -f app/ui/live_frontend.py && echo "OK: deleted"

# main.py 无任何 live_frontend 引用
grep -c "live_frontend" app/main.py
# 期望：0

# 默认访问拿到新版
curl -s http://localhost:8000/ | grep -c '/static/js/app.jsx'
# 期望：1

# ?legacy=1 已无效（应仍返回新版或 ignored）
curl -s "http://localhost:8000/?legacy=1" | grep -c '/static/js/app.jsx'
# 期望：1（query 参数被忽略，仍返回新版）

# 后端测试全过（确认无意外影响）
python -m pytest tests/ -v 2>&1 | tail -3
```

**变更摘要**：`refactor(ui): remove legacy live_frontend.py [P4 complete]`

**push**：`git push origin main`

**Step-3 退出条件**：
- `app/ui/live_frontend.py` 不存在
- `grep -r "live_frontend" app/` 无引用
- 默认访问拿到新版
- `python -m pytest tests/ -v` 全过
- TASK.md P4 标记 [x]

---

## 6. 风险与缓解

| 风险 | 缓解 Task / 措施 |
|---|---|
| Babel Standalone 多文件加载失败 | A.1 PoC 已实测：子选项 ii（ESM import）失败，已切到子选项 i（UMD + window globals），后续 Phase B-H 全部基于子选项 i |
| NS.b 命名空间错挂 / 读取顺序错（导致 `Cannot read properties of undefined`） | 各 .jsx 文件末尾必先 `window.AppX = window.AppX || {}` 再赋值；index.html `<script>` 标签按 utils → services → common → charts → panels → 顶层 → app.jsx 顺序排 |
| className 复制时空格 / 引号偏移 | F.1 验证脚本 grep 标志性 className |
| 图表 title 字符串被改 | E.x / F.x 搬运后 grep title 字符串与 chart_builder.py 对齐 |
| props 漏传导致交互失效 | F.4 / G.2 搬运前先 read 调用点确认 props 全集；E.2 / E.3 / G.2 任何 props 数量超预期 → 停下问 |
| RichCreditPanel inline SVG 抽组件后视觉偏差 | F.4 替换后立即浏览器 `?next=1` 比对；偏差 → 停下问 |
| Step-2 切换默认后才发现深层 bug，?legacy=1 失效 | Step-2.1 验证 `?legacy=1` 仍可达；任何质疑 → 不进入 Step-3 |
| `app/main.py` import 残留（HTMLResponse / Request） | Step-3.1 grep 验证 |
| Windows / WSL 路径分隔符问题 | `STATIC_DIR = Path(__file__).resolve().parent / "static"`（Step 3 已用绝对路径，跨平台安全） |
| live_frontend.py 在搬运过程中被其他窗口编辑 | 每个 Phase commit 前先 `git status --short`；如出现无关改动 → 停下汇报 |

---

## 7. Out of Scope（不做）

- 重构 className 为语义 CSS
- 引入 TypeScript / Vite / npm
- 加 SSE / WebSocket / 轮询
- 改图表库
- 视觉回归自动化测试（Playwright / Storybook / 截图 diff）
- 修改 `app/ui/mock_frontend.py`
- 修改 `data_acquisition_agent/`、`app/api/`、`app/services/`、`app/runtime_skills/`、`app/schemas/`、`tests/`、`.agents/skills/`
- 删除 `app/ui/` 目录本身（Step-3 后 mock_frontend.py 仍在该目录）

---

## 8. Task 总数与时间估算

| 阶段 | Task 数 | 每 Task | 累计 |
|---|---|---|---|
| Step-1 / Phase A（PoC） | 2 | 5 min | 10 min |
| Step-1 / Phase B（utils） | 4 | 4 min | 26 min |
| Step-1 / Phase C（services） | 1 | 3 min | 29 min |
| Step-1 / Phase D（common） | 5 | 4 min | 49 min |
| Step-1 / Phase E（charts） | 3 | 5 min | 64 min |
| Step-1 / Phase F（panels） | 5 | 5 min | 89 min |
| Step-1 / Phase G（顶层 + 入口） | 3 | 5 min | 104 min |
| Step-1 / Phase H（main.py 路由） | 1 | 3 min | 107 min |
| Step-1 收尾验证 | — | 10 min | 117 min |
| Step-2 | 1 | 5 min | 122 min |
| Step-3 | 1 | 5 min | 127 min |

总 26 个 Task，纯搬运/路由改动累计约 2.5 小时；外加每个 Phase 后的浏览器目视验证额外开销。

汇报节奏：每个 Phase 完成后停下汇报等用户确认；单个 Task 内遇到歧义 / PoC 失败 / 视觉偏差 / import 失败时立即停下。

---

## 9. 后续

- Step-1 完成后：Step 7 交付（已合 main + 已 push github）
- Step-2 / Step-3 完成后：Step 8 白盒审计（重点确认 className / chart title / API 契约无意外改动）
- mock_frontend.py 处理：本 Plan 不涉及，单独评估
