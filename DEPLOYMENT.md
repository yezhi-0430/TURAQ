# TURAQ 部署指南

这个文档介绍如何将 TURAQ (A股智能研究平台) 部署到生产环境，让其他人可以访问。

## 方案 1：本地运行 + 局域网分享 (最快速)

适合临时演示或内部团队使用。

### 步骤：

1. **启动服务**
```bash
# 设置环境变量
export ANTHROPIC_API_KEY=your_key_here

# 启动后端（允许外部访问）
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. **获取你的 IP 地址**
```bash
# Windows
ipconfig

# Mac/Linux
ifconfig | grep "inet "
```

3. **分享访问地址**
将你的 IP 告诉其他人，例如：`http://192.168.1.100:8000`

**优点**: 零成本，立即可用  
**缺点**: 仅限同一局域网，你的电脑需要保持开机

---

## 方案 2：Docker 部署 (推荐 ⭐⭐⭐)

使用 Docker 可以快速部署到任何云服务器。

### 前置要求：
- 安装 Docker 和 Docker Compose
- 一台云服务器（阿里云、腾讯云、AWS 等）

### 步骤：

1. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入真实的 API Key 和数据库密码
```

2. **启动所有服务**
```bash
docker-compose up -d
```

3. **查看日志**
```bash
docker-compose logs -f web
```

4. **访问应用**
打开浏览器访问：`http://your-server-ip:8000`

### 管理命令：

```bash
# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看运行状态
docker-compose ps

# 更新代码后重新构建
docker-compose up -d --build
```

---

## 方案 3：云平台一键部署

### Railway.app (支持国内访问)

1. 注册 Railway 账号：https://railway.app
2. 连接你的 GitHub 仓库
3. 添加环境变量：
   - `ANTHROPIC_API_KEY`
   - `DATABASE_URL` (Railway 会自动提供 PostgreSQL)
4. 点击部署

**优点**: 自动 HTTPS，全球 CDN  
**费用**: 免费额度 $5/月，超出按用量计费

### Render.com

1. 注册 Render 账号：https://render.com
2. 新建 Web Service，连接 GitHub
3. 设置构建命令：`pip install -e .`
4. 设置启动命令：`uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. 添加 PostgreSQL 数据库
6. 设置环境变量

**优点**: 免费套餐可用，自动 SSL  
**缺点**: 国内访问可能较慢

### 阿里云/腾讯云轻量应用服务器

1. 购买轻量应用服务器（¥60-100/月）
2. 选择 Ubuntu 22.04 系统
3. SSH 连接服务器
4. 安装 Docker：
```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl start docker
sudo systemctl enable docker
```
5. 上传代码到服务器
6. 运行 `docker-compose up -d`
7. 配置防火墙开放 8000 端口

---

## 前端构建与托管

当前页面入口为 `frontend/index.html`。在项目根目录构建：

```powershell
npm ci --prefix frontend
npm run build --prefix frontend
```

将生成的 `frontend/dist/` 作为静态目录提供，并在同一 HTTPS 站点把 `/api/` 转发到后端；该目录的 `index.html` 为首页。账号 Cookie、Origin 和 CSRF 检查需要前后端使用一致的站点配置。具体本地启动与代理设置见 [前端说明](frontend/README.md)。

旧版独立演示页面已经移除。仅托管静态文件无法完成当前需要后端的登录、研究和交易流程。

---

## 安全建议

在生产环境部署时：

1. **修改默认密码**
   - 更改 `docker-compose.yml` 中的数据库密码
   - 使用强密码

2. **保护 API Key**
   - 不要将 `.env` 文件提交到 Git
   - 使用环境变量或密钥管理服务

3. **启用 HTTPS**
   - 使用 Nginx 反向代理 + Let's Encrypt 证书
   - 或使用云平台自带的 SSL 支持

4. **添加访问控制**
   - 实现用户认证系统
   - 添加 API 访问频率限制

---

## 故障排查

### 容器启动失败
```bash
# 查看详细日志
docker-compose logs web

# 进入容器内部调试
docker-compose exec web bash
```

### 数据库连接失败
- 检查 `DATABASE_URL` 是否正确
- 确保 PostgreSQL 服务已启动
- 检查防火墙规则

### 端口被占用
```bash
# Windows: 查找占用 8000 端口的进程
netstat -ano | findstr :8000

# 杀死进程
taskkill /PID <进程ID> /F
```

---

## 推荐部署方案对比

| 方案 | 成本 | 难度 | 适用场景 |
|------|------|------|----------|
| 本地 + 局域网 | 免费 | ⭐ | 临时演示 |
| Docker + 云服务器 | ¥60-100/月 | ⭐⭐ | 正式生产环境 |
| Railway/Render | $0-20/月 | ⭐ | 个人项目/快速原型 |
| 静态托管 | 免费 | ⭐ | 仅展示前端 |

**我的推荐**：如果是正式项目，使用 Docker + 阿里云服务器；如果是快速展示原型，使用 Railway.app。
