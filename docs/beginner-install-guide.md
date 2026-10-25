# TURAQ 新手安装指南（Windows）

> 面向完全没有编程基础的人：从 GitHub 下载 TURAQ，在自己电脑上跑起来，并填写 Qwen（千问）密钥。

---

## 先看结论（重要）

1. **GitHub 上放的是源代码，不是安装包。** 点“下载 ZIP”只是把代码下载下来，不能像普通软件那样双击安装。
2. **TURAQ 目前没有官方 exe 安装包，也没有公开在线试用地址。** 仓库 Releases 为空，必须自己配置运行环境（截至 2026-10-25）。
3. 需要一次性安装三个基础软件：**Python、Node.js、PostgreSQL**；再执行几条命令。之后每次使用**双击 `一键启动.bat`** 即可。
4. 全程约 **30～60 分钟**。如果完全不懂电脑，建议找会电脑的人帮你做“第 2～7 步”，大约 20 分钟；之后你自己只会用到“双击启动”。
5. 只想先看看界面、不接 AI？可以先用 `MODEL_PROVIDER=fake`（离线测试模式）启动，不填密钥也能打开页面。

---

## 第 1 步：从 GitHub 下载代码

1. 打开仓库：<https://github.com/yezhi-0430/TURAQ>
2. 点右上角绿色的 **`<> Code`** 按钮 → **`Download ZIP`**
3. 下载得到 `TURAQ-main.zip`，解压到 **`D:\TURAQ`**（路径尽量短、不要有特殊符号；没有 D 盘就放 `C:\TURAQ`）
4. 打开 `D:\TURAQ`，确认能看到这些内容：
   - `app` 文件夹
   - `frontend` 文件夹
   - `一键启动.bat`
   - `.env.example`

> 说明：ZIP 里**没有** `.env`、`.venv`、`node_modules`，这些都要按下面的步骤自己生成。

---

## 第 2 步：安装 Python

1. 打开 <https://www.python.org/downloads/windows/>
2. 下载 **Windows installer (64-bit)**，版本 **3.12 或 3.13**（项目已验证 3.13.12）
3. 安装第一页务必勾选 **`Add python.exe to PATH`**，再点 `Install Now`
4. 装完后**重新打开**一个 PowerShell 窗口，输入：
   ```powershell
   python --version
   ```
   能显示 `Python 3.13.x` 就成功。
   - 如果弹出微软商店，说明没装好或没勾 PATH，重装并勾选 PATH。

---

## 第 3 步：安装 Node.js

1. 打开 <https://nodejs.org/>，下载 **LTS** 版本
2. 一路“下一步”默认安装
3. 重新打开 PowerShell，验证：
   ```powershell
   node -v
   npm -v
   ```
   两个都能显示版本号即可。

---

## 第 4 步：安装 PostgreSQL（数据库）

1. 打开 <https://www.postgresql.org/download/windows/>，下载 EDB 安装器（16 或 17 都可以）
2. 安装过程中：
   - 端口保持 **5432**
   - **设置并记住超级用户 `postgres` 的密码**（后面要用）
3. 安装完成后，打开开始菜单 → PostgreSQL 文件夹 → **SQL Shell (psql)**
   - 一路按回车（Server、Database、Port、Username 都用默认）
   - 提示 `Password for user postgres:` 时，输入你刚才设的 postgres 密码（输入时不显示，正常）
4. 出现 `postgres=#` 后，复制粘贴下面两行，每行回车：
   ```sql
   CREATE ROLE turaq_user LOGIN PASSWORD 'TuraqLocal2026';
   CREATE DATABASE a_share_risk_agent OWNER turaq_user;
   ```
   > 密码 `TuraqLocal2026` 可以换成你自己的，但要和后面 `.env` 里写的一致。
5. 输入 `\q` 回车退出。

> 如果端口 5432 被占用，安装时改成 5433，并记住，后面 `.env` 的 `DATABASE_PORT` 也要改成 5433。

---

## 第 5 步：安装项目依赖（只需一次）

1. 打开 `D:\TURAQ` 文件夹
2. 在文件夹空白处**右键** → **在终端中打开**（Windows 11）
   - 或按住 `Shift` + 右键 → **在此处打开 PowerShell 窗口**
   - 或打开 PowerShell 后执行：`cd D:\TURAQ`
3. 依次执行下面三条命令，**每条等它跑完再执行下一条**：

```powershell
python -m venv .venv

.\.venv\Scripts\python.exe -m pip install -e '.[dev]'

npm --prefix frontend ci
```

- 第一条创建项目专用 Python 环境（生成 `.venv` 文件夹）
- 第二条安装后端依赖，通常要 3～10 分钟
- 第三条安装前端依赖（生成 `frontend\node_modules`）

> 如果下载太慢，可换国内镜像（可选）：
> ```powershell
> .\.venv\Scripts\python.exe -m pip install -e '.[dev]' -i https://pypi.tuna.tsinghua.edu.cn/simple
> npm --prefix frontend ci --registry=https://registry.npmmirror.com
> ```

---

## 第 6 步：创建并编辑 `.env` 配置文件

1. 在 `D:\TURAQ` 里，把 **`.env.example`** 复制一份，重命名为 **`.env`**
   - 注意：文件名就是 `.env`，**不要变成 `.env.txt`**
   - 资源管理器 → 顶部“查看” → 勾选 **文件扩展名**，方便确认
2. 用**记事本**打开 `.env`，修改下面这些行（其余保持不动）：

```ini
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_NAME=a_share_risk_agent
DATABASE_USER=turaq_user
DATABASE_PASSWORD=TuraqLocal2026

MODEL_PROVIDER=qwen
MODEL_NAME=qwen-plus
DASHSCOPE_API_KEY=sk-这里粘贴你的千问密钥
```

- `DATABASE_PASSWORD` 填第 4 步你设置的密码
- `DASHSCOPE_API_KEY` 就是 Qwen 密钥（下一节讲去哪拿）。注意 `.env.example` 里这一行默认是**注释**（开头有 `#`）：把 `#` 删掉再填，或直接在文件末尾新起一行写 `DASHSCOPE_API_KEY=sk-...`
- `MODEL_PROVIDER` 默认是 `fake`，要改成 `qwen` 才会真正调用千问模型
- `SITE_BASE_URL` 不用改，`一键启动.bat` 会自动按 `http://localhost:3000` 启动
- **暂时没有密钥**：把 `MODEL_PROVIDER=qwen` 改成 `MODEL_PROVIDER=fake`，其余先不动，也能启动看界面
- 保存时编码选 **UTF-8**

> `.env` 里保存的是密码和密钥，**不要发给别人、不要截图、不要上传 GitHub**。该文件已被项目自动忽略，不会上传。

---

## 第 7 步：建数据库表 + 创建你的登录账号

仍在 `D:\TURAQ` 的 PowerShell 窗口里执行：

```powershell
.\.venv\Scripts\python.exe -c "from app.database import create_tables; create_tables()"

.\.venv\Scripts\python.exe -m app.auth.admin bootstrap-admin --email 你的邮箱@example.com --verified-email
```

- 第一条：在数据库里创建所有表（无输出即成功）
- 第二条：创建管理员账号。看到 `Password:` 后输入密码（**6～15 位**，输入时不显示），回车，最后显示 `管理员 ID: 1` 即成功
- 这个邮箱 + 密码就是后面登录用的账号，**记下来**

> 为什么不用网页注册？因为网页注册需要发验证邮件，本机没配邮箱服务器（SMTP）发不出去。用上面命令直接创建“已验证管理员”是最简单的本地用法。

---

## 第 8 步：启动 TURAQ

1. 双击项目根目录的 **`一键启动.bat`**
2. 会弹出一个黑色窗口，自动检查环境、启动后端和前端（约 10～30 秒）
3. 成功后会自动打开浏览器：**<http://localhost:3000>**
4. 用第 7 步的邮箱和密码登录

补充：

- 关闭黑色窗口**不会**停止服务；要停止请双击 **`停止服务.bat`**
- 浏览器没自动打开，就手动访问 <http://localhost:3000>
- 不要直接双击 `frontend\index.html`，那样登录和接口都不工作
- 启动失败时看日志：`.local-backups\launcher\backend.log`、`frontend.log`

---

## 第 9 步：Qwen（千问）密钥填在哪里？

有两个位置，**任选一种即可**。

### 方式 A：写进 `.env` 文件（新手推荐，最简单）

在 `D:\TURAQ\.env` 中设置：

```ini
MODEL_PROVIDER=qwen
MODEL_NAME=qwen-plus
DASHSCOPE_API_KEY=sk-你的密钥
```

保存后：如果服务正在运行，先双击 `停止服务.bat`，再双击 `一键启动.bat` 重新启动。

验证：登录后打开“研究助手”，问一句“用一句话解释市盈率”。如果返回正常文字，说明密钥已生效；如果提示需要 `DASHSCOPE_API_KEY`，说明 `.env` 没保存成、或没重启。

### 方式 B：登录后在网页“系统设置”里填（仅管理员）

1. 用管理员账号登录 <http://localhost:3000>
2. 点左侧 **「系统设置」**
3. 选 **「模型服务」** 分类（标签写着 `ADMIN / 全站管理`）
4. **模型供应商** 选择 `Qwen 在线模型`
5. 在 **「模型 API 密钥」** 输入框粘贴 `sk-...`
6. 点 **「加密保存密钥」**，保存后立即生效

前提：`.env` 里必须配置 `SETTINGS_ENCRYPTION_KEY`（用于加密密钥），否则页面会提示“在线更新需要先在部署环境配置 SETTINGS_ENCRYPTION_KEY”，按钮不可用。

生成方法（在 `D:\TURAQ` 的 PowerShell 里执行）：

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出的一整串字符写进 `.env`：

```ini
SETTINGS_ENCRYPTION_KEY=刚才生成的那一串
```

然后重启服务，再回到网页保存密钥。

> 说明：界面保存的密钥会加密存进数据库，页面不会回显；“恢复部署密钥”按钮会删除数据库里的覆盖值，改用 `.env` 里的密钥。普通注册用户看不到“模型服务”这个分类，只有管理员能改全站密钥。

---

## 第 10 步：Qwen 密钥去哪申请？

1. 打开阿里云百炼（通义千问）控制台：<https://bailian.console.aliyun.com/>
2. 用阿里云账号登录，按提示**开通百炼服务**（通常需要实名认证）
3. 进入 **API-KEY / API 密钥管理** → **创建我的 API-KEY**
4. 复制生成的密钥（一般以 `sk-` 开头），粘贴到第 6 步或第 9 步的位置

其他信息：

- 默认接口地址（`.env.example` 里已写好）：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 默认模型：`qwen-plus`
- 官方获取说明：<https://help.aliyun.com/zh/model-studio/get-api-key>
- 费用、免费额度、限流以百炼控制台页面为准；不用时可在控制台停用或删除密钥
- **密钥泄露**：立刻去控制台删除旧密钥并重新创建，然后更新 `.env`

---

## 常见问题

| 现象 | 原因 / 解决 |
| --- | --- |
| 双击 `一键启动.bat` 后窗口一闪而过，或提示“未找到项目 Python 环境” | 第 5 步没做，或 `.venv` 没生成；重新执行 `python -m venv .venv` 和 pip 安装 |
| 提示“缺少 .env” | 第 6 步没做；确认文件名是 `.env` 不是 `.env.txt` |
| 提示“数据库账号/自选表尚未初始化” | 第 7 步建表失败；检查 PostgreSQL 是否启动、`.env` 里数据库密码是否正确 |
| 数据库连接失败 | PostgreSQL 服务没运行（开始菜单搜“服务”，找 `postgresql-x64-16`）；端口不是 5432；密码错 |
| 提示端口 3000 或 8888 被占用 | 先双击 `停止服务.bat`；仍不行就关闭占用端口的程序，或重启电脑 |
| 页面打开但登录不了 | 用第 7 步创建的管理员邮箱+密码；网页注册需要 SMTP，本机默认发不了邮件 |
| 模型回答像“测试内容” | `MODEL_PROVIDER` 还是 `fake`，改成 `qwen` 并重启 |
| 模型报 401 / 额度不足 | 密钥错误、欠费或额度用尽；去百炼控制台检查 |
| 上传 PDF / 知识库报缺少依赖 | 安装可选依赖（较大，按需）：<br>`.\.venv\Scripts\python.exe -m pip install chromadb sentence-transformers PyPDF2 python-docx python-multipart` |
| 想彻底重装 | 删除 `.venv`、`frontend\node_modules` 后从第 5 步重来；数据库可删库重建 |

---

## 安全与边界提醒

- 这是**本地开发环境**：默认只监听本机，没有 HTTPS，不要直接放到公网。
- `.env` 含数据库密码和模型密钥，已被 `.gitignore` 忽略；**永远不要**把它提交到 GitHub 或发给别人。
- 行情、公告来自公开数据源，可能延迟、缺失或不可用；分析结果仅用于学习研究，**不构成投资建议**。
- 项目是“源码 + 本地运行”形态；没有官方安装包、没有公开在线地址，属于正常情况，不是下载失败。

---

## 最简操作清单（给会电脑的人看）

```powershell
# 0) 安装 Python 3.13（勾 PATH）、Node.js LTS、PostgreSQL 16/17
# 1) 解压到 D:\TURAQ
cd D:\TURAQ

# 2) 依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
npm --prefix frontend ci

# 3) 数据库（SQL Shell / pgAdmin 执行）
# CREATE ROLE turaq_user LOGIN PASSWORD 'TuraqLocal2026';
# CREATE DATABASE a_share_risk_agent OWNER turaq_user;

# 4) 复制 .env.example 为 .env，填写 DATABASE_* 和 DASHSCOPE_API_KEY

# 5) 建表 + 管理员
.\.venv\Scripts\python.exe -c "from app.database import create_tables; create_tables()"
.\.venv\Scripts\python.exe -m app.auth.admin bootstrap-admin --email you@example.com --verified-email

# 6) 双击 一键启动.bat，浏览器打开 http://localhost:3000
```

Qwen 密钥位置：`.env` 里 `DASHSCOPE_API_KEY=sk-...`（并把 `MODEL_PROVIDER` 设为 `qwen`）；或登录管理员后「系统设置 → 模型服务 → 模型 API 密钥」。
