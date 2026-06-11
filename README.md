# 短剧行业数据看板

> **作者**: Bridget Yang
> **版本**: v1.7.14
> **更新**: 每日北京时间9:00自动更新

---

## 📊 功能概览

- **剧集榜单TOP20**: 每日更新的短剧播放量排行榜
- **演员热力榜TOP10**: 女频/男频演员各10人
- **行业快讯5条**: 每条100字深度洞察分析
- **行业洞察**: 具体事件+真实数据
- **题材分布**: 题材占比+热门标签
- **观众画像**: 基于当日TOP10剧目题材爽点动态反推性别/年龄/地域/行为标签
- **APP月活/剧集总量**: 行业宏观数据

---

## 🔗 访问地址

**GitHub Pages**: https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html

---

## 🛠 技术栈

- **数据源**: Kimi (Moonshot) API 联网搜索
- **推理引擎**: DeepSeek API JSON推理
- **自动化**: GitHub Actions
- **前端**: 纯HTML + Chart.js
- **部署**: GitHub Pages

---

## 📁 项目结构

```
assets/
├── index.html       # 网页看板
└── data/
    ├── latest.json  # 最新数据
    └── history/     # 历史数据

src/
├── graphs/          # LangGraph工作流
│   ├── nodes/       # 节点实现
│   ├── state.py     # 状态定义
│   └── graph.py     # 图编排
├── tools/           # API工具
│   ├── moonshot_api.py  # Kimi搜索
│   └── deepseek_api.py  # DeepSeek推理
└── run_github.py    # GitHub Actions入口
```

---

## 🚀 本地运行

```bash
# 安装依赖
uv sync

# 运行工作流（需要API Keys）
export MOONSHOT_API_KEY=your_api_key
export DEEPSEEK_API_KEY=your_api_key
python src/run_github.py
```

---

## 📖 详细文档

- [AGENTS.md](AGENTS.md) - **项目规范和节点清单（必读）**
- [docs/DEPLOY.md](docs/DEPLOY.md) - 部署指南
- [docs/DUAL_AI_ARCHITECTURE.md](docs/DUAL_AI_ARCHITECTURE.md) - 双AI架构说明
