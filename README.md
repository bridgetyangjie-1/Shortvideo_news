# 短剧行业数据看板

> 作者：Bridget Yang  
> 当前版本：v1.8.0  
> 更新频率：每日北京时间 9:00 自动更新

## 功能概览

- 剧集榜单 TOP20：每日短剧播放热度排行，红果官网直爬504部短剧数据。
- 前端榜单 TOP8：展示层必须严格有 8 条；生成链路少于 8 条会补齐或拒绝发布，避免页面只显示 1-2 条。
- 演员热力榜：女频 TOP10 + 男频 TOP10。
- 行业快讯：固定 5 条，每条包含 250-350 字四段式深度摘要，覆盖事件核心、数据支撑、商业洞察和决策价值。
- 行业大事件：具体事件 + 真实数据，避免泛泛趋势描述。
- 题材分布：题材占比和热门标签。
- 观众画像：性别、年龄、地域分布。
- 行业宏观数据：APP 月活、AI 短剧渗透率、剧集总量、破亿爆款剧等。
- H5响应式适配：支持PC端和移动端浏览，榜单滚动加载（初始20条，点击加载更多）。

## 在线访问

GitHub Pages: https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html

## 技术栈

| 模块 | 技术 |
|---|---|
| 数据采集 | 红果官网直爬（HongguoCrawler） |
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
    ├── all_history.json
    └── history/

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
