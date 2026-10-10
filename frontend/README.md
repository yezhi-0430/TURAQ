# A股风险监控 Agent - 前端

基于 React 18 + Vite 构建的深色主题前端界面。

## 快速开始

### 安装依赖

```bash
cd frontend
npm install
```

### 启动开发服务器

```bash
npm run dev
```

前端将在 `http://localhost:3000` 启动，API 请求会自动代理到后端 `http://127.0.0.1:8000`。

### 构建生产版本

```bash
npm run build
```

## 项目结构

```
frontend/
├── src/
│   ├── components/      # 可复用组件
│   │   └── Layout.jsx   # 整体布局（导航+头部）
│   ├── pages/           # 页面组件
│   │   ├── AgentPage.jsx        # AI 研究助手（核心展示）
│   │   ├── DashboardPage.jsx    # 行情驾驶舱
│   │   ├── WatchlistPage.jsx    # 自选管理
│   │   ├── RiskPage.jsx         # 风险监控
│   │   ├── TradingPage.jsx      # 模拟交易
│   │   └── SettingsPage.jsx     # 系统设置
│   ├── styles/          # 样式文件
│   │   └── global.css   # 全局样式和设计 Token
│   ├── App.jsx          # 根组件
│   └── main.jsx         # 入口文件
├── index.html
├── vite.config.js
└── package.json
```

## 功能特性

### Phase 1（已完成）✅

- ✅ 深色主题设计系统
- ✅ 左侧导航 + 顶部状态栏布局
- ✅ **AI 研究助手页面**（核心展示）
  - 对话式界面
  - 工具调用可视化
  - 执行轨迹展示（参数、结果、耗时、状态）
  - 模拟计算演示

### Phase 2（待开发）

- ⏳ 自选管理（CRUD 功能）
- ⏳ 风险监控（结构化输出展示）
- ⏳ 后端 API 对接

### Phase 3（待开发）

- ⏳ 行情驾驶舱
- ⏳ 模拟交易页面
- ⏳ 系统设置

## 设计系统

### 色彩 Token

```css
--surface-0: #05070C    /* 最深背景 */
--surface-1: #0A0D12    /* 卡片背景 */
--surface-2: #0F131C    /* 悬停状态 */
--surface-3: #161D2B    /* 输入框背景 */
--surface-4: #1E2636    /* 按钮背景 */

--text-primary: #E5E7EB     /* 主要文本 */
--text-secondary: #9CA3AF   /* 次要文本 */
--text-tertiary: #6B7280    /* 禁用文本 */

--accent-cyan: #38BDF8      /* 链接、信息 */
--accent-green: #6EE7B7     /* 成功、涨 */
--accent-red: #F87171       /* 风险、跌 */
--accent-amber: #FCD34D     /* 警告 */
```

### 技术栈

- React 18
- Vite 5
- CSS Modules
- 原生 Fetch API

## 当前状态

**AI 研究助手**是当前唯一完整实现的页面，展示了：
- Agent 多轮对话
- 工具调用的完整执行流程
- 结果可视化

目前使用**模拟数据**进行演示。真实 API 对接将在 Phase 2 完成。

## 面试展示建议

1. 直接打开 AI 研究助手页面
2. 输入示例问题（如"从 10 到 9 的变化率"）
3. 展示工具调用的可视化流程
4. 说明这是基于你实际后端 Agent 能力的 UI 展示
