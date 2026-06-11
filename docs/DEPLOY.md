# 短剧行业数据工作流 - 本地部署指南

## 第一步：环境准备

### 1.1 检查Python版本
```bash
python --version
# 需要 Python 3.10+
```

### 1.2 安装uv（包管理器）
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 第二步：获取项目代码

### 方式A：从Coze Coding下载
在Coze Coding项目页面，下载整个项目代码包

### 方式B：Git克隆（如果有仓库）
```bash
git clone <仓库地址>
cd <项目目录>
```

---

## 第三步：安装依赖

```bash
# 进入项目目录
cd /path/to/project

# 安装所有依赖
uv sync
```

---

## 第四步：启动服务

### 4.1 启动HTTP服务
```bash
# 方式一：前台运行（调试用）
uv run python src/main.py

# 方式二：后台运行（生产用）
nohup uv run python src/main.py > logs/server.log 2>&1 &

# 方式三：指定端口
PORT=8080 uv run python src/main.py
```

### 4.2 检查服务是否启动
```bash
# 查看进程
ps aux | grep main.py

# 测试接口
curl http://localhost:9000/health
```

---

## 第五步：调用接口

### 5.1 基础调用
```bash
curl -X POST http://localhost:9000/run \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 5.2 保存结果到文件
```bash
curl -X POST http://localhost:9000/run \
  -H "Content-Type: application/json" \
  -d '{}' -o assets/data.json
```

### 5.3 指定日期查询
```bash
# data_date使用当日日期，如：2026-06-11
curl -X POST http://localhost:9000/run \
  -H "Content-Type: application/json" \
  -d '{"data_date": "今日日期"}'
```

---

## 第六步：配置定时任务

### 6.1 编辑crontab
```bash
crontab -e
```

### 6.2 添加定时任务（每天早8点执行）
```bash
# 每天早8点更新数据
0 8 * * * cd /path/to/project && uv run python src/main.py >> logs/cron.log 2>&1

# 或者用curl调用
0 8 * * * curl -X POST http://localhost:9000/run -H "Content-Type: application/json" -d '{}' -o /path/to/project/assets/data.json
```

---

## 第七步：前端对接

### 7.1 读取本地JSON文件
```javascript
// 方式一：fetch本地文件（需要HTTP服务器）
fetch('/assets/data.json')
  .then(res => res.json())
  .then(data => {
    console.log(data.rankings);
  });

// 方式二：直接调用API
fetch('http://localhost:9000/run', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({})
})
  .then(res => res.json())
  .then(data => {
    console.log(data);
  });
```

### 7.2 动态HTML直接打开
```bash
# 直接在浏览器打开（HTML会自动加载latest.json数据）
open assets/index.html

# 注意：HTML通过fetch动态加载JSON数据，不要写死数据！
# 工作流每次运行更新JSON，HTML会自动显示最新数据
```

---

## 常见问题

### Q1: 端口被占用怎么办？
```bash
# 查看9000端口占用
lsof -i :9000

# 杀掉进程
kill -9 <PID>

# 或使用其他端口
PORT=8080 uv run python src/main.py
```

### Q2: 如何部署到服务器？

**1. 上传代码到服务器**
```bash
scp -r /local/project user@server:/home/user/project
```

**2. SSH登录服务器**
```bash
ssh user@server
cd /home/user/project
```

**3. 安装依赖并启动**
```bash
uv sync
nohup uv run python src/main.py > logs/server.log 2>&1 &
```

**4. 开放端口（防火墙）**
```bash
# CentOS
firewall-cmd --add-port=9000/tcp --permanent
firewall-cmd --reload

# Ubuntu
ufw allow 9000
```

**5. 外网访问**
```bash
curl http://服务器公网IP:9000/run -X POST -H "Content-Type: application/json" -d '{}'
```

### Q3: 如何查看日志？
```bash
# 实时查看日志
tail -f logs/server.log

# 或查看工作流日志
tail -f /app/work/logs/bypass/app.log
```

---

## 目录结构

```
project/
├── assets/
│   ├── data.json          # 工作流输出的JSON数据
│   ├── index.html         # 动态HTML看板（fetch加载JSON）
│   └── history_data.json  # 历史数据存储
├── src/
│   ├── main.py            # 服务入口
│   └── graphs/            # 工作流代码
├── config/                # 大模型配置
├── docs/                  # 文档
├── logs/                  # 日志目录
└── pyproject.toml         # 依赖配置
```

---

## 一键部署脚本

创建 `deploy.sh`：
```bash
#!/bin/bash

echo "=== 短剧行业数据工作流部署 ==="

# 1. 检查Python
if ! command -v python &> /dev/null; then
    echo "请先安装Python 3.10+"
    exit 1
fi

# 2. 安装uv
if ! command -v uv &> /dev/null; then
    echo "安装uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 3. 安装依赖
echo "安装依赖..."
uv sync

# 4. 创建日志目录
mkdir -p logs

# 5. 启动服务
echo "启动服务..."
nohup uv run python src/main.py > logs/server.log 2>&1 &

echo "服务已启动，访问 http://localhost:9000"
echo "测试命令: curl -X POST http://localhost:9000/run -H 'Content-Type: application/json' -d '{}'"
```

运行：
```bash
chmod +x deploy.sh
./deploy.sh
```

---

## 第八步：GitHub Actions 自动化部署

### 8.1 配置文件位置
```
.github/workflows/daily_update.yml
```

### 8.2 功能说明
- **自动执行**：每天北京时间早9:00自动运行工作流
- **手动触发**：支持在GitHub网页手动点击按钮运行
- **自动推送**：运行完成后自动提交最新JSON数据

### 8.3 GitHub Secrets 配置（必须）
在GitHub仓库设置中添加以下Secrets：

| Secret名称 | 说明 | 获取方式 |
|------------|------|----------|
| `MOONSHOT_API_KEY` | Kimi (Moonshot) API密钥 | 从Moonshot/Kimi开放平台获取 |
| `COZE_API_KEY` | Coze API密钥（如需要） | 从Coze平台获取 |

**配置步骤**：
1. 进入GitHub仓库 → Settings → Secrets and variables → Actions
2. 点击 "New repository secret"
3. 添加上述密钥

### 8.4 工作流程图
```
GitHub服务器 (UTC 1:00 / 北京时间 9:00)
    ↓
拉取代码 (actions/checkout@v4)
    ↓
安装Python 3.12 + uv
    ↓
安装依赖 (uv pip install)
    ↓
运行工作流 (python src/run_github.py)
    ↓
生成 latest.json + history/*.json
    ↓
自动提交推送 (git commit + push)
    ↓
GitHub Pages 更新前端
```

### 8.5 手动触发测试
1. 进入GitHub仓库 → Actions
2. 选择 "🚀 Daily Short-Drama Dashboard Update"
3. 点击 "Run workflow" → "Run workflow"
4. 查看运行日志确认成功

### 8.6 查看运行结果
- 运行日志：Actions → 选择具体运行记录
- 数据更新：assets/data/latest.json
- 前端更新：GitHub Pages 自动部署
