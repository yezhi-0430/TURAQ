# K 线入场与登录过渡 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution of this small frontend change. One scoped independent review follows verification.

**Goal:** 替换首页为停留式 K 线品牌入场，登录后平滑进入工作台。

**Architecture:** `frontend/entrance.js` 负责 SVG 构建和可取消的登录过渡；`entrance.css` 负责一次性动画与响应式。`index.html` 保留工作台，替换首页并接入口；`auth.js` 将成功登录后的关闭动作交给过渡，Vite 注册新脚本。

**Tech Stack:** 原生 HTML/CSS/SVG/JavaScript、Web Animations、现有 Vite。

## Global Constraints

- 只播放一次，不点击永不自动路由；右上角登录随时可点。
- K 线从左到右生成后 Logo 渐显，减少动态偏好可静态显示。
- 只修改前端，不请求真实模型、邮件或行情，不改变登录保护。
- 保留原工作台、品牌 T 悬停转正与侧栏切换；取消过时动画以防退出后重新显示工作台。
- 不提交其他既有未提交内容。

## Task 1: 入场页与账号过渡

Files: create `frontend/entrance.js`, `frontend/entrance.css`; modify `frontend/index.html`, `frontend/auth.js`, `frontend/vite.config.js`, `frontend/README.md`; meaningful transition cases in `tests/frontend/entrance.test.mjs`.

- [x] 先验证缺少过渡控制器的失败：初始化不能发出进入事件；模拟登录动画过程中会话清理，工作台不得重新显示；减少动态时可直接切换。
- [x] 添加装饰 SVG、全屏点击按钮、右上角登录与中央 TURAQ 标记，CSS 逐根生成并渐显字标。
- [x] 接 `window.siteEntrance.enterWorkspace()` 和 `cancelTransition()`；成功登录由工作台入口关闭账号窗口，保持无动画环境回退。入口仍使用 `data-enter`，但显式打开账号窗口。
- [x] Vite 的脚本打包名单加入 `entrance`，生产资源存在检查继续执行。
- [x] 构建后运行 `node --test tests/frontend/*.test.mjs`，核对现有账号、自选与图表行为。
- [x] 在独立本地页面检查首次动画、无点击停留、即时登录、登录成功过渡、手机尺寸；使用隔离夹具，保存截图。
- [x] 对完整前端改动做一次独立代码审查，修复必要问题；记录验证与仅提交本次文件。

