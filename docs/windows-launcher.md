# Windows 一键启动

- 双击项目根目录 `一键启动.bat` 或 `start.bat`：启动前后端，自动打开浏览器。
- 双击 `停止服务.bat`：停止本项目占用 3000 / 8888 的前后端进程及其子进程。
- 关闭启动窗口不会停止后台服务。
- 命令行验收：`.\.venv\Scripts\python.exe scripts/launch_turaq.py --no-browser`；停止用 `--stop`。

启动器相对自身定位项目，不依赖双击时的工作目录。后端使用 `.venv/Scripts/python.exe`，前端使用已安装的 Node.js 和本项目 Vite。为本地启动进程设置 SITE_BASE_URL=http://localhost:3000、AUTH_COOKIE_SECURE=false 与 8888 代理目标，不改写 `.env`，不输出密钥。

端口、进程归属、后端风险路由、前端页面和实际同源登录代理全部就绪后，才报告启动成功。重复点击通过文件锁串行化；已运行且健康的本项目服务复用。其他目录/程序占用端口时退出。新服务启动失败时只回收本次启动的进程。

PostgreSQL 需已运行且 `.env` 已配置。旧的账号、自选、行情初始化规则保持不变。若仅缺少风险表，先调用 pg_dump 生成完整备份，再执行新增风险表的幂等升级；备份失败则停止启动，不修改表。

文件位置：

- `.local-backups/launcher/backend.log`：后端输出。
- `.local-backups/launcher/frontend.log`：前端输出。
- `.local-backups/launcher/schema.log`：首次风险表准备的备份工具输出。
- `.local-backups/launcher/*-before-risk.dump`：升级前数据库备份。
- `.local-backups/launcher-original/start.bat`：修改前启动脚本。

2026-10-13 验证：4 项隔离测试通过；实际停止并冷启动两项服务通过；从其他工作目录执行中文批处理入口通过；重复启动 PID 不变；前端 3000 → 后端 8888 的登录会话代理正常。首次运行已完成本机风险表备份与初始化。
