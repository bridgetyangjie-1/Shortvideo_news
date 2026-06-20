# 短剧行业数据看板

> 作者：Bridget Yang  
> 当前版本：v1.10.8  
> 更新频率：每日北京时间 9:00 自动更新

## 功能概览

- 剧集榜单 TOP20：每日短剧播放热度排行，以短剧工程周榜为坐标、红果推荐页追踪每日变化。
- 前端榜单 TOP20：展示层必须严格有 20 条；生成链路少于 20 条会补齐或拒绝发布，避免页面只显示 1-2 条。
- 演员热力榜：女频 TOP10 + 男频 TOP10。
- 行业快讯：固定 6 条，每条包含 150-200 字四段式深度摘要，覆盖事件核心、数据支撑、商业洞察和决策价值。
- 行业大事件：具体事件 + 真实数据，避免泛泛趋势描述。
- 题材分布：近7天热门标签按题材/人设/爽点/情感/时代分类聚合，每个维度独立取 TOP N 避免单一维度被挤出，并展示标签环比异动。
- 观众画像：性别、年龄、地域、题材偏好、观看时段、付费能力与用户分层。
- 行业宏观数据：APP 月活、AI 短剧渗透率、剧集总量、破亿爆款剧等。
- H5响应式适配：支持PC端和移动端浏览，榜单滚动加载（初始20条，点击加载更多）。

## 内容供应链（IP Source Tracking）

本看板追踪短剧的上游 IP 来源，包括：
- 番茄小说网文改编
- 原著书名/作者关联
- 改编匹配度评分

数据展示：
- 榜单中 📚 标记表示该剧改编自网络小说
- 鼠标悬停显示原著书名

技术实现：
- `tools/ip_supply_chain.py`：IP 提取与匹配
- `tools/hongguo_crawler.py`：红果详情页改编信息提取
- `push_node.py`：供应链数据归档

## 在线访问

GitHub Pages: https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html

## 技术栈

| 模块 | 技术 |
|---|---|
| 数据采集 | 短剧工程周榜（DuanjugongchengCrawler）+ 红果推荐页（HongguoCrawler） |
| 本地缓存 | SQLite缓存（避免重复搜索） |
| 联网搜索 | Kimi / Moonshot API |
| JSON 推理 | DeepSeek API |
| 工作流编排 | Python |
| 自动化 | GitHub Actions |
| 前端 | 静态 HTML + Chart.js（H5响应式） |
| 托管 | GitHub Pages |

## 目录结构

```text
assets/
├── index.html
└── data/
    ├── latest.json
    ├── latest_full.json
    ├── all_history.json
    ├── history/
    │   └── YYYY-MM-DD.json
    └── weekly/
        └── YYYY-MM-DD.json

config/
└── *_llm_cfg.json

src/
├── graphs/
│   ├── graph.py
│   ├── state.py
│   └── nodes/
├── tools/
│   ├── moonshot_api.py
│   └── deepseek_api.py
└── run_github.py
```

## 本地运行

需要 Python 3.12、`uv`，以及两个 API key。

```bash
uv sync

export MOONSHOT_API_KEY=your_moonshot_key
export DEEPSEEK_API_KEY=your_deepseek_key
export PYTHONPATH="$PWD/src"

uv run python src/run_github.py
```

运行后主要输出：

- `assets/data/latest.json`
- `assets/data/all_history.json`
- `assets/data/history/*.json`

## GitHub Actions

自动化入口：`.github/workflows/daily_update.yml`

- 触发时间：UTC 1:00，即北京时间 9:00。
- 手动触发：支持 `workflow_dispatch`。
- 必需 secrets：
  - `MOONSHOT_API_KEY`
  - `DEEPSEEK_API_KEY`
- 可选 secret：
  - `MOONSHOT_BASE_URL`

## 前端数据约定

`assets/index.html` 位于 `assets/` 目录下，因此数据必须使用相对路径读取：

```javascript
fetch('./data/latest.json')
```

不要在 HTML 中写死指标数据。Python 工作流只负责输出 JSON，前端负责动态渲染。

## 文档入口

- `AGENTS.md`：给编码 agent 的当前工作规则，保持精简。
- `docs/ROADMAP.md`：已知风险、改进优先级和后续方向。

为减少 token 消耗和误导，仓库不再保留大型历史总结、旧部署方案或重复架构说明类 Markdown。
