# 短剧行业数据看板

> **作者**: Bridget Yang
> **版本**: v1.5.0
> **更新**: 每日北京时间9:00自动更新

---

## 📊 功能概览

- **榜单TOP10**: 每日更新的短剧播放量排行榜
- **行业快讯**: 5条精选新闻，100字总结，附带原文链接
- **行业大事件**: 具体事件+真实数据（如播放量暴涨45%）
- **题材分布**: 题材占比+热门标签（背景/主题/设定）
- **演员热力榜**: 女频/男频演员TOP10
- **观众画像**: 性别/年龄/地域分布
- **平台份额**: 各平台播放量占比

---

## 🔗 访问地址

**GitHub Pages**: https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html

---

## 🛠 技术栈

- **数据源**: Kimi (Moonshot) API 联网搜索
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
├── tools/           # Kimi (Moonshot) API工具
└── run_github.py    # GitHub Actions入口
```

---

## 🚀 本地运行

```bash
# 安装依赖
uv sync

# 运行工作流（需要MOONSHOT_API_KEY）
export MOONSHOT_API_KEY=your_api_key
python src/run_github.py
```

---

## 📖 详细文档

- [AGENTS.md](AGENTS.md) - 项目规范和节点清单
- [docs/DEPLOY.md](docs/DEPLOY.md) - 部署指南
- [docs/IMPROVEMENT_ROADMAP.md](docs/IMPROVEMENT_ROADMAP.md) - 当前风险和改进路线图