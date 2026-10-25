# Langfuse Cloud真实连接验收

2026-10-24。用户选择新建Cloud项目并自行完成账号/项目和本地.env配置后，完成一次纯合成元数据验收。没有调用模型、读取业务数据库、发送业务文档或上传既有评测回答。密钥仅在子进程环境使用，报告不包含Public/Secret Key。

- 固定SDK langfuse==5.0.4安装到项目.venv。此前真实SDK+Mock HTTP验证脚本重新通过。
- 真实项目认证通过；经app.observability现有后台队列与LangfuseSink发送两个事件，同一trace另有明确synthetic标记。
- 队列drained=true、failed=0、dropped=0、pending=0。
- 从服务端Observations API v2回查3条observation，确认generation合成input=3/output=2/total=5；Scores API回查requested/passed/scored均为1。
- 原始结果与trace链接：[cloud-smoke-2026-10-24.json](../../evaluations/turaq/langfuse/results/cloud-smoke-2026-10-24.json)；[验证记录](../../evaluations/turaq/langfuse/results/verification-2026-10-24.json)。该usage为合成连通性数据，不是实际模型消耗。

启动检查发现：Pydantic读取.env不会自动把值写入os.environ，而Langfuse开关读取进程环境。新增启动回归先复现缺少--env-file，再给一键启动后端命令补参数。手工启动说明同步更新；前端启动不加载此文件。子进程测试确认uvicorn在应用导入前加载配置，启用适配器时仍不导入业务数据库或提前连接SDK。

安装SDK后完整隔离unit 572通过（3个既有依赖弃用警告）；启动修复后launcher/observability针对性13通过，含2项新增回归；Ruff、compileall、diff检查通过。用户.env与密钥未改写；报告已用本地内存比对确认不含密钥。

检查时本项目后端8888、前端3000均未运行，因此没有业务服务需要重启，也未自动启动业务服务。今后通过一键启动或uvicorn --env-file .env启动后，进程会加载追踪配置。真实Cloud链路已验收，不代表既有进程已启用或真实业务调用已验证。未提交、推送或部署。
