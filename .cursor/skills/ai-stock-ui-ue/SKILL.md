---
name: ai-stock-ui-ue
description: 轻舟版 A 股交易决策系统的 UI/UE 设计规范（Vue 3 + Element Plus Web 端 + UniApp 小程序端）。Web 端为全暗色交易终端风格（TradingView 配色），使用 CSS 变量 + Element Plus `html.dark` 暗色模式。当进行新页面开发、现有界面改进、UI 一致性检查、组件选型或 UX 决策时使用此 skill。
---

# 轻舟版交易系统 UI/UE 设计规范

## 产品定位

A 股短线交易决策支持系统，非自动交易。核心决策链路：
**市场环境 → 板块扫描 → 个股筛选 → 买点 → 卖点 → 账户适配 → 执行输出**

## 技术栈

- **Web 管理后台**：Vue 3 + Element Plus 2.5 + Vue Router 4 + Axios（无全局状态管理）
- **Element Plus 暗色模式**：`frontend/index.html` 中 `<html class="dark">`，`main.js` 引入 `element-plus/theme-chalk/dark/css-vars.css`
- **微信小程序**：UniApp + Vue 3，纯原生组件（无 UI 库）

---

## 设计系统（Design Token）— 暗色终端

业务 Token 定义在 `frontend/src/App.vue` 的 `:root` 中；`html.dark` 内覆盖 `--el-*` 与 EP 暗色主题对齐。

```css
:root {
  --color-bg:       #131722;   /* 主背景深蓝黑 */
  --color-card:     #1e222d;   /* 卡片 / 侧边栏 / Header */
  --color-hover:    #2a2e39;   /* hover / 次级块背景 */
  --color-border:   #2a2e39;   /* 边框 */
  --color-text-pri: #d1d4dc;   /* 主要文字 */
  --color-text-sec: #787b86;   /* 次要/标签文字 */
  --color-brand:    #e02020;   /* 品牌红（Logo 左侧条） */
  --color-primary:  #2962ff;   /* 主色蓝（激活/主按钮） */
  --color-up:       #f23645;   /* 涨/危险/卖出（TradingView 红） */
  --color-down:     #089981;   /* 跌/安全/可执行（TradingView 绿） */
  --color-neutral:  #d4a017;   /* 中性/观察/谨慎 */
  --shadow-card:    0 2px 8px rgba(0, 0, 0, 0.4);
}
```

**颜色语义——A 股习惯（红涨绿跌）：**

| 类名 | Token | 用途 |
|------|--------|------|
| `.text-up` / `.text-red` | `--color-up` `#f23645` | 涨幅、止损、卖出 |
| `.text-down` / `.text-green` | `--color-down` `#089981` | 跌幅、可执行、安全 |
| `.text-neutral` / `.text-yellow` | `--color-neutral` `#d4a017` | 中性、谨慎、观察 |

---

## 整体布局（Web）

```
<html class="dark">
el-container（height: 100vh）
├── el-aside（200px，--color-card，右侧 border）
│   ├── .logo（深底 + 左侧 4px 品牌红条）
│   └── el-menu（激活：左侧 3px --color-primary + --color-hover 背景）
└── el-container
    ├── el-header（--color-card，底部 border + 阴影）
    └── el-main（背景 --color-bg，padding: 20px）
```

---

## 核心 UI 模式

### 卡片 Header（统一规范）

```vue
<el-card>
  <template #header>
    <div class="card-header">
      <span>卡片标题</span>
      <el-button @click="loadData" :loading="loading">刷新</el-button>
    </div>
  </template>
</el-card>
```

```css
.card-header { display: flex; justify-content: space-between; align-items: center; }
```

### Dashboard 摘要数值

- 四宫格主数值：`font-size: 22px; font-weight: 700`
- 带 `text-red` / `text-green` / `text-yellow` 时需在 scoped 内用 `.summary-item .value.text-*` 提高优先级，避免覆盖全局涨跌色

### 市场情绪指标卡（Market）

- 指标块背景：`--color-hover`，边框 `--color-border`
- 涨停数 / 跌停数：数值加 `value-emphasis`，`font-size: 32px`

### 数据加载三态

```vue
<el-skeleton v-if="loading" :rows="5" animated />
<template v-else>
  <el-empty v-if="!data.length" description="暂无数据" />
  <el-table v-else :data="data" />
</template>
```

### 涨跌幅着色

```vue
<span :class="row.change_pct > 0 ? 'text-red' : 'text-green'">
  {{ row.change_pct?.toFixed(2) }}%
</span>
```

### el-tag 状态语义

| 市场环境 | el-tag type |
|---------|------------|
| 进攻 | `danger` |
| 中性 | `warning` |
| 防守 | `success` |

---

## 7 个页面规范

| 页面 | 路径 | 核心特征 |
|------|------|---------|
| Dashboard | `/` | `Promise.all` 并发 6 个 API，骨架屏，摘要大字 22px |
| 市场环境 | `/market` | 环境标签 + 评分 + 情绪四卡（涨停/跌停 32px 强调） |
| 板块扫描 | `/sectors` | `el-tabs` 4 类，弱市时自动切「全部行业」 |
| 三池分类 | `/pools` | `el-tabs` 3 池，**禁止同表混写** |
| 买点分析 | `/buy` | 顶部 `el-alert` 市场环境，2 tab |
| 卖点分析 | `/sell` | 3 tab，`sell_priority` |
| 账户管理 | `/account` | 概况 + 持仓表 + `el-dialog` 新增 |

---

## UE 设计原则（业务特有）

1. **信息密度优先**：表格 > 卡片装饰
2. **全局市场状态可感知**：`进攻/中性/防守` 在 Dashboard 与买卖点可见
3. **三池严格分离**：禁止同表混写
4. **风险信号高对比**：止损/卖出用 `--color-up`，不得弱化
5. **决策链路即导航顺序**
6. **当前版本无图表**

---

## 新页面开发 Checklist

- [ ] `html` 已 `class="dark"`，不单独写浅色 EP 主题
- [ ] 骨架屏 / 空态 / `ElMessage` 错误
- [ ] 卡片 header 刷新按钮 `:loading`
- [ ] 涨跌色：`text-red` / `text-green`，scoped 内注意优先级
- [ ] 颜色用 CSS 变量，避免硬编码 `#909399` 等

---

## 小程序端规范（UniApp）

- 无 Web 端 `dark` 类；可用深灰背景 + 红 `#f23645` / 绿 `#089981` 与 Web 语义对齐
- 支持下拉刷新：`onPullDownRefresh` + `uni.stopPullDownRefresh()`
