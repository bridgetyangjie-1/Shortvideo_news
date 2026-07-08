# 短剧行业数据看板 - Agent 工作规则

> 本文是给 AI 编码代理阅读的当前有效规则。历史方案、过期部署说明和一次性项目总结不要放入本文件。
> 项目对外介绍、运行方式请见 `README.md`，改进计划请见 `docs/ROADMAP.md`。

## 1. 项目概述

这是一个自动化的**短剧行业数据看板**系统。每天北京时间 9:00（UTC 1:00）由 GitHub Actions 触发，爬取短剧工程周榜（基于红果官方周榜）为主、红果推荐页为辅，补充演员与厂牌信息、生成行业快讯与洞察，最终输出静态 JSON 数据，托管在 GitHub Pages 上供前端展示。

- **项目名称**：`shortvideo-news`
- **当前版本**：`v1.14.5`
- **在线地址**：https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html
- **数据入口**：`assets/data/latest.json`（TOP20 展示）、`assets/data/latest_full.json`（Full100 归档）、`assets/data/weekly/YYYY-MM-DD.json`（周榜归档，每周一）
- **GitHub Actions 入口**：`src/run_github.py`
- **前端入口**：`assets/index.html`

核心能力包括：

- 剧集榜单 TOP20（前端 TOP20 必须严格 20 条）
- 演员热力榜（女频 TOP10 + 男频 TOP10）
- 每日行业快讯 6 条
- 行业大事件洞察
- 题材分布与热门标签
- 观众画像
- 行业宏观数据（APP 月活、AI 短剧渗透率、剧集总量等）
- 🤖 AI 短剧/漫剧看板（月度 KPI、AI 仿真人剧 TOP5、AI 漫剧 TOP5、趋势洞察、行业快讯）

## 2. 技术栈

| 模块 | 技术 |
|---|---|
| 包管理 | `uv` + `hatchling` |
| Python 版本 | `>=3.11`（GitHub Actions 使用 3.12） |
| 工作流编排 | `langgraph>=0.2.0` + `langchain-core>=0.3.0` |
| 数据模型 | `pydantic>=2.0.0` |
| HTTP/爬虫 | `httpx>=0.27.0`、`requests>=2.31.0` |
| 联网搜索 | Moonshot/Kimi API（`openai>=1.0.0`） |
| JSON 推理 | DeepSeek API |
| 本地缓存 | SQLite（`src/tools/cache_db.py`） |
| 服务层（仅 Coze 场景） | `fastapi>=0.115.0` + `uvicorn>=0.30.0` + `cozeloop>=0.1.28` |
| Prompt 模板 | `Jinja2>=3.1.0` |
| 前端 | 单文件静态 HTML + Chart.js + ECharts，H5 响应式 |
| 托管 | GitHub Pages |

## 3. 项目结构

```text
.
├── .github/workflows/daily_update.yml   # GitHub Actions 自动化工作流
├── assets/
│   ├── index.html                       # 前端看板页面
│   ├── history_data.json                # 周榜热度趋势与周榜历史（以周为粒度）
│   └── data/
│       ├── latest.json                  # TOP20 展示数据
│       ├── latest_full.json             # 全量榜单（可达 100 条）
│       ├── all_history.json             # 近 30 天历史索引
│       ├── history/YYYY-MM-DD.json      # 按日归档
│       └── weekly/YYYY-MM-DD.json       # 周榜归档（每周一）
├── config/                              # LLM 提示词与模型配置
│   └── *_llm_cfg.json
├── docs/
│   └── ROADMAP.md                       # 风险与改进路线图
├── scripts/                             # 本地/HTTP 运行脚本
│   ├── local_run.sh
│   ├── http_run.sh
│   └── setup.sh
├── src/
│   ├── main.py                          # Coze/FastAPI 服务入口（仅 Coze 场景）
│   ├── run_github.py                    # GitHub Actions 专用入口
│   ├── graphs/
│   │   ├── graph.py                     # LangGraph 工作流编排
│   │   ├── state.py                     # Pydantic 状态模型入口（re-export，保持兼容）
│   │   ├── models/                      # 按领域拆分的状态模型
│   │   │   ├── ranking.py               # 榜单与演员
│   │   │   ├── industry.py              # 行业与平台
│   │   │   ├── audience.py              # 观众画像
│   │   │   ├── genre.py                 # 题材与标签
│   │   │   ├── emotion.py               # 情绪分析
│   │   │   ├── history.py               # 历史与趋势
│   │   │   ├── news.py                  # 洞察与快讯
│   │   │   ├── ai_drama.py              # AI 短剧/漫剧看板模型
│   │   │   └── node_io.py               # 各节点 Input/Output
│   │   ├── ranking_quality.py           # TOP20 榜单数量质量门禁
│   │   └── nodes/                       # 12 个处理节点
│   │       └── enrich/                  # enrich_node 子模块（缓存/爬虫/搜索/JSON推理解耦）
│   ├── tools/                           # 爬虫与 API 客户端
│   ├── storage/                         # 数据库/S3/内存存储抽象
│   ├── coze_coding_utils/               # Coze Coding 平台兼容层
│   └── utils/
├── tests/
│   └── test_ranking_quality.py          # 质量门禁单元测试
├── pyproject.toml                       # Python 包配置
└── uv.lock                              # uv 依赖锁定
```

## 4. 构建与运行命令

项目使用 `uv` 作为唯一包管理器，不要直接用 `pip` 安装。

```bash
# 安装依赖（会创建 .venv）
uv sync

# 本地运行完整工作流（推荐）
export MOONSHOT_API_KEY=your_moonshot_key
export DEEPSEEK_API_KEY=your_deepseek_key
export PYTHONPATH="$PWD/src"
uv run python src/run_github.py

# 仅运行单元测试
python -m unittest tests.test_ranking_quality
# 或
uv run python -m unittest tests.test_ranking_quality

# Coze 场景下启动 HTTP 服务（本地调试用）
./scripts/http_run.sh -p 8000
# 或
uv run python src/main.py -m http -p 8000
```

CI 中的安装方式：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv sync
```

## 5. 运行时架构与入口

### 5.1 两个入口的边界

| 入口 | 文件 | 用途 | 是否可用于 GitHub Actions |
|---|---|---|---|
| **GitHub Actions 入口** | `src/run_github.py` | 生产环境标准入口，纯命令行，无 Coze SDK 依赖 | ✅ 必须使用 |
| **Coze/HTTP 入口** | `src/main.py` | 启动 FastAPI 服务，提供 `/run`、`/stream_run`、`/node_run`、`/v1/chat/completions` 等接口 | ❌ 禁止 |

**硬性规则**：GitHub Actions 运行时不要依赖 Coze 内部 SDK。`src/main.py` 和 `coze_coding_utils/` 只用于 Coze Coding 场景，外部自动化以 `src/run_github.py` 为准。

### 5.2 `src/run_github.py` 流程

1. 将项目根目录加入 `sys.path`，并设置 `COZE_WORKSPACE_PATH` 为项目根目录。
2. 从 `graphs.graph` 导入 `create_graph()`。
3. 构造输入 `{"data_date": "YYYY-MM-DD"}`。
4. 调用 `graph.invoke(input_data, config)`。
5. 依赖 `push_node` 已经保存文件，本文件只输出摘要日志。

### 5.3 图编排（`src/graphs/graph.py`）

工作流由 LangGraph 状态图编排，状态模型为 `GlobalState`：

```
search_node
    ├──→ news_node ──┐
    ├──→ process_node─┘
    └──→ ai_drama_node
              ↓
        enrich_node
              ↓
        actor_ranking_node
              ├──→ industry_node ──┐
              └──→ audience_profile_node─┘
                            ↓
                    genre_distribution_node
                            ↓
              ┌──── emotion_analysis_node
              │
              ↓
            insights_node
              ↓
        history_data_node ──┐
                            ├→ quality_gate_node
        ai_drama_node ──────┘
                            ↓
                      should_push_data
                        /          \
                 alert_node        END
                      ↓
                   push_node
                      ↓
                     END
```

- `news_node` 与 `process_node` 在 `search_node` 后并行；`ai_drama_node` 与两者并行，但**不再直接汇入 `push_node`**，而是与 `history_data_node` 一起汇入 `quality_gate_node`，避免 `push_node` 在主流程完成前被提前触发。
- `industry_node` 与 `audience_profile_node` 在 `actor_ranking_node` 后并行。
- `emotion_analysis_node` 与 `insights_node` 在 `genre_distribution_node` 后并行。
- `push_node` 前为 `quality_gate_node`：校验榜单数量、字段完整性、演员榜、快讯来源、行业数据、API 错误，失败或质量分低于 60 分时直接结束工作流，不覆盖 `latest.json`。

## 6. 代码组织

### 6.1 `src/graphs/nodes/` 节点层

| 节点 | 文件 | 主要功能 | 是否依赖 LLM |
|---|---|---|---|
| `search_node` | `search_node.py` | 短剧工程周榜为主 + 红果推荐页为辅 + DataEye 交叉验证 + 1 次 Kimi 行业宏观搜索 | 否（爬虫）+ Kimi 1 次 |
| `process_node` | `process_node.py` | 优先处理短剧工程周榜；用红果推荐页补充 series_id/cover/tags/episodes；均无数据时用 Kimi 兜底 | 否（主路径）/ 是（Kimi 兜底） |
| `enrich_node` | `enrich_node.py` | 本地缓存 → 红果详情页爬虫 → Kimi 批量补充 → DeepSeek 生成完整 JSON | 是（DeepSeek/Kimi） |
| `actor_ranking_node` | `actor_ranking_node.py` | 从 enriched_rankings 统计演员频次，生成女频/男频 TOP10；DeepSeek 补充仅在周一触发 | 否（统计）/ 周一 DeepSeek 兜底 |
| `industry_node` | `industry_node.py` | 搜索行业宏观数据，输出 IndustryData + PlatformData | 是（Kimi） |
| `audience_profile_node` | `audience_profile_node.py` | 月度行业报告基准（Kimi 搜索）+ 每日 TOP20 榜单信号/环比趋势/分析师洞察；搜索失败时降级为本地规则 | 是（Kimi，每月最多 1 次） |
| `genre_distribution_node` | `genre_distribution_node.py` | 近7天榜单加权聚合标签频次，按题材/人设/爽点/情感/时代分类，并计算标签环比趋势 | 否 |
| `emotion_analysis_node` | `emotion_analysis_node.py` | 从 `config/emotion_rules.json` 加载情绪维度规则，基于当日榜单规则化统计情绪维度；DeepSeek 提炼总览、TOP3 情绪剧目与行动建议；失败或兜底时基于实际统计数据动态生成文案 | 是（DeepSeek） |
| `insights_node` | `insights_node.py` | 周更：周一 Kimi 搜索行业事件 → DeepSeek 生成商业洞察并缓存；周二至周日直接读缓存 | 是（Kimi+DeepSeek，每周最多 1 次） |
| `news_node` | `news_node.py` | Kimi 搜索 3 组新闻 → DeepSeek 生成最多 6 条快讯 | 是（Kimi+DeepSeek） |
| `ai_drama_node` | `ai_drama_node.py` | 月度 DataEye AI 短剧/漫剧月报/百强榜 + 独立行业报道：优先直爬 thepaper 多篇报告，按发布节奏自动回退月份，输出 KPI、AI 仿真人剧 TOP5、AI 漫剧 TOP5（含剧情简介/标签/制作方/链接）、带来源引用的趋势洞察、带摘要的行业快讯；月度缓存，平日直接读取 | 是（Kimi/DeepSeek，每月最多 1 次） |
| `history_data_node` | `history_data_node.py` | 生成周榜热度趋势（近8周）、周榜历史、排名变化 | 否 |
| `quality_gate_node` | `quality_gate_node.py` | 统一质量门禁：校验榜单/演员/快讯/行业数据/API 错误 | 否 |
| `alert_node` | `alert_node.py` | 异常监测：基于质量报告与业务规则自动生成 Alerts | 否 |
| `push_node` | `push_node.py` | 保存 latest.json、latest_full.json、历史归档、周榜归档（周一）、all_history.json | 否 |

### 6.2 `src/tools/` 工具层

| 工具 | 文件 | 作用 |
|---|---|---|
| `DuanjugongchengCrawler` | `duanjugongcheng_crawler.py` | 爬取 `duanjugongcheng.com/cn/bangdan/`，获取基于红果官方周榜的 TOP50 榜单（主数据源） |
| `HongguoCrawler` | `hongguo_crawler.py` | 爬取 `novelquickapp.com` 首页 `_ROUTER_DATA`，获取最多 100 条推荐列表（仅作元数据补充） |
| `DataEyeCrawler` | `dataeye_crawler.py` | 爬取 DataEye 热力榜，用于交叉验证（当前 API 不稳定，作为可选补充） |
| `CacheDB` | `cache_db.py` | SQLite 本地缓存，7 天有效期，存储演员/工作室/标签 |
| `TagNormalizer` | `tag_normalizer.py` | 标签同义词映射、题材分类（female/male/neutral） |
| `MoonshotClient` | `moonshot_api.py` | Kimi 客户端：chat、search、JSON 提取、429 退避、API 预算熔断 |
| `DeepSeekClient` | `deepseek_api.py` | DeepSeek 客户端：chat 接口 |
| `AIDramaCache` | `ai_drama_cache.py` | AI 短剧/漫剧看板月度缓存 |
| `AIDramaFetcher` | `ai_drama_fetcher.py` | 澎湃新闻 DataEye 月报直爬 + 规则抽取 |

### 6.3 `src/storage/` 存储层

- `storage/database/db.py`、`storage/shared/model.py`：数据库模型。
- `storage/memory/memory_saver.py`：内存存储。
- `storage/s3/s3_storage.py`：S3 存储抽象。
- **当前实际数据持久化由 `push_node.py` 直接写本地 JSON 完成**，存储层代码保留但非主路径。

### 6.4 `src/coze_coding_utils/`

Coze Coding 平台兼容层，仅在 `src/main.py` 场景使用：

- `runtime_ctx/context.py`：运行时上下文。
- `log/`：日志配置与解析。
- `error/classifier.py`：错误分类。
- `openai/handler.py`：OpenAI 兼容接口。

## 7. 数据流说明

1. **search_node**：爬取短剧工程周榜 TOP50（或首页 TOP10）作为主数据源；抓取红果官网 100 条推荐页作为辅助；尝试 DataEye 30 条交叉验证；再用 Kimi 搜索 1 次行业宏观数据。
2. **news_node**：并行运行，Kimi 搜索 3 组新闻 → DeepSeek 生成 ≤6 条快讯。
3. **ai_drama_node**：与 `news_node`/`process_node` 并行，月度运行。月初/缓存缺失时按发布节奏（默认次月 18 日前后）选择最近完整报告月，直爬 thepaper 上 DataEye AI 短剧/漫剧月报/百强榜（`config/ai_drama_articles.json`）及独立行业报道，经 DeepSeek 抽取 KPI、TOP5 榜单（含 `plot`/`tags`/`studio`/`url`）、带 `source`/`source_url` 的趋势洞察、带 `summary` 的行业快讯；平日读取 `data/ai_drama_cache.json` 缓存。仅收录真正的 AI 仿真人剧、AIGC/3D/2D AI 漫剧，排除普通沙雕漫。
4. **process_node**：优先解析 `duanjugongcheng_ranking` 中的短剧工程周榜，转换为标准榜单（`weekly_index` 作为 `heat`/`views_num`）；用红果推荐页回填 `series_id`、`cover`、`tags`、`episodes`；短剧工程不可用时降级使用红果推荐页；均不可用时用 Kimi 从搜索结果提取。
4. **enrich_node**：对前 20 条，先查 SQLite 缓存，再爬红果详情页，Kimi 批量搜索补充，最后 DeepSeek 生成完整榜单 JSON。
5. **actor_ranking_node**：从 enriched_rankings 统计演员出现频次，生成女频/男频 TOP10；男女频不足 10 人时，仅在周一调用 DeepSeek 推理补充，平日保留榜单提取结果以节省 token。
6. **industry_node**：用 Kimi 搜索行业宏观数据，结合榜单 AI/女男频比例，输出 IndustryData。
7. **audience_profile_node**：以自然月为粒度缓存行业报告画像（性别/年龄/地域/付费/分层等基准）。月初/缓存缺失时 Kimi 搜索权威报告；每日从 TOP20 榜单加权统计「本周信号」（女频浓度、题材权重、AI/新剧占比），与昨日历史归档对比生成环比趋势与分析师洞察；前端双层展示「本周信号(周更)」vs「行业基准(月更)」。
8. **genre_distribution_node**：读取近7天历史榜单加权聚合标签（今日权重最高），按本地 taxonomy 分为题材/人设/爽点/情感关系/时代背景等类别，并计算较昨日的 `trending` 趋势。
9. **emotion_analysis_node**：从 `config/emotion_rules.json` 加载情绪维度规则（可按月审视更新），基于 `enriched_rankings` 的题材/标签映射到情绪、焦虑、触发点等维度并加权统计；调用 DeepSeek 生成总览摘要、TOP3 情绪剧目、行动建议与环比趋势；DeepSeek 失败或兜底时，summary 与 actionable_insights 基于当日实际统计数据动态生成，避免固定文案。
10. **insights_node**：周更节点。周一使用 Kimi 搜索行业事件 → DeepSeek 生成商业洞察并写入 `tools/weekly_cache.py` 周缓存；周二至周日命中缓存时直接返回，不重复调用 API。缓存缺失时（如首次运行）会兜底生成。
11. **history_data_node**：更新 `assets/history_data.json`，以周为粒度生成周榜热度趋势（`daily` 由 `weekly_rankings` 派生，每周一个点，避免同一周热度重复写入），同时生成周榜历史与排名变化。
12. **quality_gate_node**：统一校验榜单、演员、快讯、行业数据与 API 错误，输出 `quality_report`。
13. **alert_node**：基于质量报告与业务规则自动生成 `alerts`，供前端异常面板展示。
14. **push_node**：输出 `latest.json`（TOP20）、`latest_full.json`（全量）、`assets/data/history/YYYY-MM-DD.json`、`assets/data/weekly/YYYY-MM-DD.json`（每周一，当数据源为短剧工程时）、`assets/data/all_history.json`；同时在 `latest.json`/`latest_full.json` 中写入 `weekly_base` 字段供前端展示周榜 TOP1 坐标。

## 8. 编码规范

### 8.1 Python

- 使用 **Pydantic v2** 模型定义状态，属性访问使用 `obj.field_name`，不要假设可用 `.get()`。
- 节点函数签名统一参考：

  ```python
  def node_name(state: InputModel, config: RunnableConfig, runtime: Runtime[Context]) -> OutputModel:
      ...
  ```

- 节点返回 Pydantic 模型，通常包含 `success`、`error_message` 字段。
- 对 API 错误做熔断：`is_api_budget_error()`，API 调用上限 30 次/客户端。
- 大量使用 `model_dump()` 序列化 Pydantic 对象。
- 日志使用 `logging.getLogger(__name__)`。

### 8.2 模型配置约定

每个 `config/*_llm_cfg.json` 包含：

- `config.model`：模型名称、温度、max_tokens、top_p。
- `sp`：system prompt。
- `up`：user prompt 模板（Jinja2 语法，含 `{{date}}`、`{{rankings}}` 等占位符）。

| 配置 | 当前模型 |
|---|---|
| `config/news_llm_cfg.json` | `deepseek-chat` |
| `config/insights_llm_cfg.json` | `deepseek-chat` |
| `config/actor_ranking_llm_cfg.json` | `deepseek-chat` |
| `config/enrich_llm_cfg.json` | `deepseek-chat` |
| `config/industry_llm_cfg.json` | `moonshot-v1-32k` |
| `config/ai_drama_llm_cfg.json` | `moonshot-v1-32k` |

### 8.3 前端

- `assets/index.html` 在 `assets/` 目录下，数据路径必须使用相对路径：

  ```javascript
  fetch('./data/latest.json')
  ```

- Python 节点只输出 JSON，不拼接或覆盖 HTML。
- 前端渲染对象字段时必须展开属性，避免显示 `[object Object]`。
- 不要把指标数据写死进 HTML。

## 9. 测试说明

- **测试文件**：
  - `tests/test_ranking_quality.py`：榜单数量质量门禁
  - `tests/test_quality_gate.py`：统一数据质量门禁（P0）
  - `tests/test_alert_node.py`：异常监测节点规则测试（P1）
  - `tests/test_config_validation.py`：LLM 配置文件校验（P1）
  - `tests/test_node_functions.py`：核心节点纯函数单元测试（P1）
- **框架**：`unittest`
- **测试内容**：
  1. `test_uses_recent_history_to_reach_top20`：用历史数据补齐到 20 条。
  2. `test_raises_when_sources_cannot_reach_top20`：来源不足时抛出 `RankingCountError`。
  3. `test_passes_with_complete_data` / `test_fails_when_*`：质量门禁通过/失败路径。
  4. `test_valid_config_passes` / `test_invalid_*_fails`：配置文件与 Jinja2 模板校验。
  5. `test_merge_*`、`test_fill_unknown_*`、`test_infer_profile_*`、`test_classify_tag` 等：节点内部纯函数。

运行：

```bash
python -m unittest tests.test_ranking_quality tests.test_quality_gate tests.test_alert_node tests.test_config_validation tests.test_node_functions
```

新增节点或修改状态模型时，应补充对应单元测试。测试数据使用临时目录，不要依赖真实 API key。

配置文件校验命令：

```bash
export COZE_WORKSPACE_PATH="$PWD"
python src/utils/config_validator.py
```

## 10. 数据规则与质量门禁

### 10.1 数据采集优先级

1. **短剧工程周榜**：`tools/duanjugongcheng_crawler.py` 抓取 `duanjugongcheng.com/cn/bangdan/`，基于红果官方周榜数据，每周一更新 TOP50，含排名、剧名、题材、本周热播指数、累计指数、上架日期、是否新剧。
2. **红果推荐页**：`tools/hongguo_crawler.py` 抓取 `novelquickapp.com` 首页推荐列表，获取 100 条，仅用于补充 `series_id`、`cover`、`tags`、`episodes` 等元数据，以及追踪周榜剧在推荐页的位置变化。
3. **Kimi 搜索补充**：行业宏观数据、标签分布、演员信息等。
3. **历史数据兜底**：近 7 天归档数据用于补齐不足 20 条的榜单。

### 10.2 时间铁律

- 所有搜索关键词必须使用当前运行日期或 `state.data_date` 动态生成。
- 禁止硬编码年份作为“今日数据”条件。
- 今日数据不足时，行业快讯可补充近 7 天重要动态，但要避免把往年数据当作今日数据。

### 10.3 榜单与演员规则

- 剧集榜单目标为 TOP20。
- 前端“榜单 TOP20”必须严格显示 20 条；`rankings` 少于 20 条时必须补齐或拒绝发布，禁止直接覆盖 `latest.json`。
- 质量门禁文件：`src/graphs/ranking_quality.py`，常量 `REQUIRED_TOP_RANKING_COUNT = 20`。
- 补齐顺序：当前输出 → supplemental_rankings → 近 7 天历史归档。仍不足 20 条则抛 `RankingCountError`。
- 演员榜为女频 TOP10 + 男频 TOP10。
- 演员搜索优先多轮检索：
  1. `短剧《{title}》主演女演员男主角`
  2. `《{title}》短剧演员阵容DataEye红果`
  3. `短剧 {title} 主演是谁 小红书抖音豆瓣`
- 演员字段不要填“未知”；搜索失败时按女频/男频常见短剧演员进行合理推理补充。

### 10.4 行业快讯规则

- `daily_news` 必须返回 6 条。
- 每条必须包含 `insight` 字段，约 100 字，覆盖行业影响、趋势判断、商业机会或风险。
- 每条必须包含具体 `source_url`，避免只给门户首页。
- 类型限定为数据、预警、商业等清晰分类。
- `content` 输出 150-200 字四段式内容，依次覆盖 `【事件核心】`、`【数据支撑】`、`【商业洞察】`、`【决策价值】`，JSON 字符串内使用 `\n` 转义换行。

### 10.5 核心数据结构

| 字段 | 类型 | 要求 |
|---|---|---|
| `rankings` | `List[DramaRanking]` | TOP20 短剧榜单 |
| `daily_news` | `List[DailyNews]` | 0-6 条快讯，每条须有真实 source_url |
| `insights` | `List[Insight]` | 具体行业事件，必须含真实数据 |
| `genre_distribution` | `GenreDistribution` | 题材分布、标签热度、分类标签、标签趋势；含 `data_source`/`update_frequency` |
| `actors` | `ActorRanking` | 女频/男频演员榜 |
| `industry` | `IndustryData` | APP 月活、AI 短剧渗透率、剧集总量等；含 `data_source`/`update_frequency` |
| `audience_profile` | `AudienceProfile` | 性别、年龄、地域、题材偏好、观看时段、付费能力、用户分层；含 `weekly_signals`/`weekly_trends`/`analyst_insights`；含 `data_source`/`update_frequency` |
| `alerts` | `List[AlertItem]` | 自动异常监测告警列表 |
| `alert_count` | `int` | 告警数量 |
| `quality_report` | `Dict[str, Any]` | 质量门禁 8 项检查详情 |
| `weekly_base` | `Dict[str, Any]` | 周榜基准信息：本周 TOP1 剧名、热度、题材、数据说明 |
| `ai_drama_dashboard` | `AIDramaDashboard` | 🤖 AI 短剧/漫剧看板：月度 KPI、AI 剧/漫剧 TOP5（含 `plot`/`tags`/`studio`/`url`）、带来源的趋势洞察、带 `summary` 的行业快讯；含 `data_source`/`update_frequency` |

## 11. 部署流程

### 11.1 GitHub Actions

- **工作流文件**：`.github/workflows/daily_update.yml`
- **触发条件**：
  - 定时：`cron: '0 1 * * *'`（UTC 1:00 = 北京时间 9:00）
  - 手动：`workflow_dispatch`
- **权限**：`contents: write`（用于自动提交生成的数据文件）

执行步骤：

1. `actions/checkout@v4` 拉取 `main` 分支。
2. `actions/setup-python@v5` 设置 Python 3.12。
3. 安装 `uv` 并执行 `uv sync`。
4. 设置环境变量：
   - `MOONSHOT_API_KEY`
   - `MOONSHOT_BASE_URL`（可选）
   - `DEEPSEEK_API_KEY`
   - `PYTHONPATH=${GITHUB_WORKSPACE}/src`
5. 运行 `uv run python src/run_github.py`。
6. 如有变更，提交并推送：`git commit -m "auto: 每日数据更新"`。

### 11.2 GitHub Pages

- 前端直接读取同目录下 `./data/latest.json`。
- 数据文件提交到仓库后由 GitHub Pages 自动托管。

## 12. 环境变量与 Secrets

### 12.1 GitHub Actions 必需 Secrets

| 名称 | 用途 |
|---|---|
| `MOONSHOT_API_KEY` | Kimi/Moonshot API 鉴权 |
| `DEEPSEEK_API_KEY` | DeepSeek API 鉴权 |

### 12.2 可选 Secrets / 环境变量

| 名称 | 用途 |
|---|---|
| `MOONSHOT_BASE_URL` | 覆盖默认 Moonshot base URL（默认 `https://api.moonshot.cn/v1`） |
| `MOONSHOT_MODEL` | 覆盖 chat 模型（默认 `moonshot-v1-32k`） |
| `MOONSHOT_SEARCH_MODEL` | 覆盖搜索模型 |
| `COZE_WORKSPACE_PATH` | `run_github.py` 自动设置为项目根目录，用于定位 `config/`、`assets/` |
| `PYTHONPATH` | 必须包含 `src/` |

## 13. 安全与合规

- **不要把 API key 写进代码或配置文件**。仅在环境变量或 GitHub Secrets 中注入。
- **不要在 HTML 中写死指标数据**。所有指标必须由 Python 工作流输出 JSON 后前端动态渲染。
- **不要用大段 mock 数据修补榜单**。数据不足时应触发补齐逻辑或拒绝发布。
- **不要只依赖 prompt 约束数据质量**，应增加代码层校验（如 `ranking_quality.py`）。
- 修改涉及外部 API 调用时，注意保留 `is_api_budget_error()` 熔断逻辑，避免无限重试导致费用失控。
- 新增依赖时必须写入 `pyproject.toml` 并执行 `uv sync` 更新 `uv.lock`。
- 不要运行 `git commit`、`git push`、`git reset`、`git rebase` 等 git 变更操作，除非用户明确授权。

## 15. 飞书机器人推送

### 15.1 功能说明

每日工作流生成 `latest.json` 后，自动通过飞书群机器人 webhook 推送一张**完整版交互式日报卡片**到指定群组；质量门禁失败时改为推送告警卡片。推送失败不影响主流程，仅记录日志。

### 15.2 环境变量

| 名称 | 用途 | 是否必填 |
|---|---|---|
| `FEISHU_WEBHOOK` | 飞书机器人 webhook 地址 | ✅ |
| `FEISHU_WEBHOOK_SECRET` | 飞书签名密钥（未配置时不启用签名校验） | 可选 |

GitHub Actions 中已通过 `${{ secrets.FEISHU_WEBHOOK }}` 注入，详见 `.github/workflows/daily_update.yml`。

### 15.3 推送内容模块

| 报告类型 | 触发条件 | 包含模块 |
|---|---|---|
| **日报** | 周二~周日 | 榜单 TOP5、今日黑马、行业快讯 TOP1、异常监测（极简，只看每日变化） |
| **周报** | 每周一 | 日报内容 + 演员热力 TOP3、行业快讯 TOP3、今日洞察、题材 & 标签风向标、情绪驾驶舱、周榜热度趋势 |
| **月报** | 每月 1 日 | 周报内容 + 行业宏观数据（用户规模/市场规模/APP月活/AI占比）、平台月活、核心观众画像 |

卡片按类型递进：日报最精简，月报最完整。

### 15.4 手动触发

```bash
# 按日期自动判断日报/周报/月报并推送
./scripts/push_feishu.sh

# 强制发送指定类型
./scripts/push_feishu.sh --daily
./scripts/push_feishu.sh --weekly
./scripts/push_feishu.sh --monthly

# 发送告警测试卡片
./scripts/push_feishu.sh --alert

# 只构建卡片并打印，不发送
./scripts/push_feishu.sh --dry-run

# 推送其他数据文件
./scripts/push_feishu.sh --data assets/data/latest_full.json
```

也可直接调用 Python 模块：

```bash
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
export PYTHONPATH="$PWD/src"
.venv/bin/python -m src.tools.feishu_pusher              # 自动判断
.venv/bin/python -m src.tools.feishu_pusher --weekly    # 强制周报
.venv/bin/python -m src.tools.feishu_pusher --monthly   # 强制月报
```

### 15.5 代码位置

- 核心实现：`src/tools/feishu_pusher.py`
- 工作流接入：`src/graphs/nodes/push_node.py`（保存数据成功后调用 `push_daily`，质量门禁失败时调用 `push_alert`）
- 手动脚本：`scripts/push_feishu.sh`
- CI 环境变量：`.github/workflows/daily_update.yml`

## 14. 开发约定

- **入口选择**：本地完整运行使用 `src/run_github.py`；Coze 平台调试使用 `src/main.py`。
- **路径约定**：所有基于项目根目录的路径通过 `COZE_WORKSPACE_PATH` 解析，不要写死绝对路径。
- **新增节点**：必须在 `src/graphs/graph.py` 中注册，输入输出模型定义在 `src/graphs/models/node_io.py` 中。
- **新增数据模型**：按领域放入 `src/graphs/models/` 下对应文件（如榜单模型放 `ranking.py`、观众画像放 `audience.py`），然后在 `src/graphs/state.py` 中 re-export 以保持兼容。
- **新增 LLM 调用**：优先复用 `MoonshotClient`/`DeepSeekClient`，注意 API 预算熔断逻辑。
- **修改 AGENTS.md 中提到的文件/流程后，必须同步更新本文件**。
- 不再新增大型历史总结类 Markdown；旧方案如需保留，优先压缩成 README 或 ROADMAP 的一小节。

## 15. 近期变更

| 日期 | 改动 |
|------|------|
| 2026-07-08 | **v1.14.5 演员热力榜纠偏与红果演员数据源修复**：`metadata_fetcher` 改用 `/detail?series_id=` 解析演职员表；`actor_resolver` enrich 内红果 catalog 剧名匹配回填 `series_id`，Kimi 改为短剧垂类 query；`enrich`/`actor_ranking` prompt 禁止一线明星与泛化假名，移除演员榜 DeepSeek 凑数；`data_quality` 新增 `MAINSTREAM_ACTOR_BLOCKLIST`；详见 `docs/CR-2026-07-08.md` §7 |
| 2026-07-08 | **v1.14.4 P1 分析可用性提升**：`utils/title_matcher.py` 增强红果剧名四级模糊匹配回填 `series_id`/封面/集数；`tag_normalizer` 扩展同义词，`genre_distribution_node` 爽点优先分类并输出 `by_gender` 男女频标签；`IndustryData` 新增 `market_spend` 大盘消耗 KPI；`enrich_node` 动态 `confidence_score`；前端展示质量分/置信度角标/男女频标签/月大盘消耗 |
| 2026-07-08 | **v1.14.3 P0 数据质量止血**：新增 `utils/data_quality.py` 拦截编号式幻觉演员名与模板化厂牌；`enrich` prompt/fallback 改为无信源留空、禁止编造；`quality_gate_node` 增加 `ranking_hallucination` 硬性门禁与快讯 URL/insight 校验；`news_node` 过滤 example.com 等不可信链接并自动提取 insight；榜单新增 `weekly_heat_index` 字段，前端区分「周热度」与「累计指数」 |
| 2026-07-07 | **v1.15.1 观众画像板块重构**：`audience_profile_node` 新增每日 TOP20 榜单信号（女频浓度/题材权重/AI新剧占比）、与昨日历史环比趋势、规则化分析师洞察；`AudienceProfile` 扩展 `weekly_signals`/`weekly_trends`/`analyst_insights`；前端双层展示「本周信号(周更)」vs「行业基准(月更)」，旧数据前端可从 rankings 兜底推算 |
| 2026-07-06 | **v1.15.0 AI 短剧/漫剧看板升级**：`config/ai_drama_articles.json` 补充 thepaper 5 月月报/百强榜与行业报道；`ai_drama_node` 增加发布滞后回退，直爬多篇文章并抽取 `plot`/`tags`/`studio`/`url` 等榜单字段；趋势洞察附 `source`/`source_url`，快讯带 `summary`；缓存校验要求榜单 ≥3 条；前端榜单展示剧情、标签、制作方、可点击标题 |
| 2026-06-12 | 新增 `tools/cache_db.py`：本地 SQLite 缓存，7 天内有效，避免重复搜索 |
| 2026-06-12 | 新增 `tools/tag_normalizer.py`：标签标准化与题材分类 |
| 2026-06-12 | 新增 `tools/dataeye_crawler.py`：DataEye 榜单爬取，交叉验证红果数据 |
| 2026-06-12 | `state.py` 新增字段：`confidence_score`、`data_source`、`rank_change`、`is_new` |
| 2026-06-12 | `search_node`：红果 + DataEye 双源融合，置信度加权 |
| 2026-06-12 | `enrich_node`：优先本地缓存，缓存 miss 时批量补充 |
| 2026-06-12 | `history_data_node`：计算排名变化（new/up/down/same） |
| 2026-06-22 | **v1.10.9 播放量趋势改为周榜热度趋势**：`history_data_node` 以短剧工程周榜为粒度生成趋势，`daily_play_trend` 由 `weekly_rankings` 派生，避免 0 值与同一周平线；前端「播放量趋势 (近7日)」改为「周榜热度趋势 (近8周)」|
| 2026-06-12 | `push_node`：输出 statistics/trends/anomalies 统计信息 |
| 2026-06-13 | **v1.10.0 情绪驾驶舱重构**：新增 `emotion_analysis_node`，基于榜单规则化统计情绪维度；前端情绪面板按洞察/热力/建议三 Tab 组织，含词云、TOP3 剧目、行动建议、环比趋势 |
| 2026-06-13 | `emotion_analysis_node` 词云分值改为 log1p + max-normalization，避免多个维度同时顶到 100 失去区分度 |
| 2026-06-22 | **v1.13.1 Token 优化与周更缓存**：新增 `tools/weekly_cache.py` 通用周缓存；`insights_node` 改为周更（周一 Kimi+DeepSeek 生成并缓存，平日读缓存），`actor_ranking_node` DeepSeek 补充仅在周一触发；避免周更内容每日重复消耗 API token |
| 2026-06-22 | **v1.13.0 飞书日报分级推送**：`src/tools/feishu_pusher.py` 支持日报/周报/月报三档卡片；日报精简（榜单+黑马+快讯），周报增加演员/标签/趋势/洞察/情绪，月报再增加行业宏观/平台/观众画像；`push_node` 根据 `data_date` 自动选择报告类型 |
| 2026-06-22 | **v1.12.0 数据真实性与更新频率标注**：`industry_node`/`audience_profile_node` 改为月度缓存，搜索失败或字段缺失时留空，不再返回固定默认值；`news_node` 取消 6 条强制凑数；所有主要数据模型增加 `data_source` 与 `update_frequency` 字段；`quality_gate_node` 增加数据来源真实性校验；前端移除 `mockAudienceProfile`/`mockEmotionalAnalysis`/`fallbackData` 回退，缺失数据显示 "--" 并展示更新频率标签 |
| 2026-06-22 | **v1.11.1 情绪规则外置与动态兜底**：`emotion_analysis_node` 将 `EMOTION_RULES` / `DIMENSION_CATEGORIES` 硬编码映射迁移到 `config/emotion_rules.json`，支持按月审视更新；DeepSeek 失败时的 summary 与 actionable_insights 改为基于当日实际统计数据动态生成；`_build_emotion_rankings` 默认值从实际 scores 取，避免固定兜底 |
| 2026-06-13 | **`audience_profile_node` 重构为纯本地规则推理**：基于榜单标签（tags/core_trope/genre）匹配受众画像规则，加权合并性别/年龄/地域/特征，不再调用 DeepSeek API，降低运行成本并保证 H5 前端数据格式兼容 |
| 2026-06-13 | `audience_profile_node` 精简输出：仅保留 `gender` / `age` / `regions` / `traits` 四个前端必需字段，按排名加权平均并归一化为 100 |
| 2026-06-22 | **v1.11.0 观众画像引入真实行业报告**：`audience_profile_node` 改为月度行业报告基准 + 周度榜单微调策略；新增 `tools/audience_profile_cache.py` 月度缓存；缓存缺失时调用 Kimi 搜索权威报告并解析完整画像；输出扩展为 `gender` / `age` / `regions` / `traits` / `content_preferences` / `viewing_time` / `spending_power` / `user_segments` |
| 2026-06-13 | **v1.10.1 P0 质量门禁**：新增 `quality_gate_node`，统一校验榜单数量、演员、快讯来源、行业数据与 API 错误；`IndustryData` / `DramaRanking` / `ActorRanking` 增加 Pydantic 字段校验；质量未通过时不覆盖 `latest.json` |
| 2026-06-13 | **v1.10.2 P1 工程化**：新增 `utils/config_validator.py` 对 `config/*_llm_cfg.json` 做 Pydantic + Jinja2 校验；新增 `tests/test_config_validation.py` 和 `tests/test_node_functions.py`，覆盖 search/enrich/audience/genre 节点核心纯函数 |
| 2026-06-13 | **v1.10.3 拆分 state.py**：将 808 行的 `src/graphs/state.py` 按领域拆分为 `src/graphs/models/` 下 8 个文件；`state.py` 保留为 re-export 入口，现有 `from graphs.state import X` 路径完全兼容 |
| 2026-06-13 | **v1.10.4 解耦 enrich_node**：将原 429 行的 `enrich_node.py` 拆分为 `src/graphs/nodes/enrich/` 下 5 个子模块（cache_adapter / metadata_fetcher / actor_resolver / json_refiner / fallback），主节点仅负责编排；新增 `tests/test_enrich_submodules.py` |
| 2026-06-14 | **v1.10.5 前端信息降噪**：`assets/index.html` 右侧情绪面板改为 Tab 切换 + 移动端底部滑出面板；左侧热门标签紧凑化；今日洞察摘要化（50 字内）；创作者行动建议默认折叠；隐藏情绪-焦虑-触发关联图 |
| 2026-06-14 | **v1.10.6 热门标签维度均衡**：`genre_distribution_node` 从“全局 TOP20 后分类”改为“按题材/爽点/人设/情感关系/时代背景独立取 TOP N”，保证每个维度都有多个标签；关系型标签（先婚后爱/闪婚/离婚/复婚）归入「情感关系」，扩展人设/情感关系词库；前端热门标签改为 2 列紧凑网格 |
| 2026-06-14 | **v1.10.6 情绪驾驶舱二合一**：`assets/index.html` 将「洞察」与「热力」两个 Tab 合并为「洞察」Tab（含今日洞察、关键词、情绪热力 TOP8、环比趋势），保留「建议」Tab；桌面端洞察 Tab 内采用 2 列网格（热力图 + 趋势），移动端自动堆叠 |
| 2026-06-16 | **v1.10.7 飞书机器人推送**：新增 `src/tools/feishu_pusher.py`，每日工作流完成后自动推送完整版交互式日报卡片；支持手动触发测试与质量门禁失败告警；GitHub Actions 通过 `FEISHU_WEBHOOK` secret 注入 |
| 2026-07-06 | **v1.14.2 发布链路修复**：质量门禁分级（`publish_mode: full/degraded/blocked`）；硬性失败走 `gate_fail_node` 飞书告警；`run_github.py` 失败 exit 1；演员榜平日不足时 DeepSeek 补充 |
| 2026-07-06 | **v1.14.1 AI 短剧数据渠道修复**：新增 `tools/ai_drama_fetcher.py` 直爬澎湃新闻 DataEye 月报；`ai_drama_node` 多层兜底；热门内容频道接入 GitHub Actions 每周一自动生成；详见 `docs/CR-2026-07-06.md` |
| 2026-06-20 | **v1.10.8 数据源重构（短剧工程周榜）**：红果网页端首页仅为推荐列表、DataEye API 不可用，改以 `duanjugongcheng.com` 短剧工程周榜为主数据源，红果推荐页仅作元数据补充；新增 `tools/duanjugongcheng_crawler.py`，`search_node` 与 `process_node` 优先处理短剧工程数据 |
| 2026-06-20 | **v1.10.8 周榜基准与归档**：`push_node.py` 在周一将短剧工程周榜归档为 `assets/data/weekly/YYYY-MM-DD.json`，并在 `latest.json`/`latest_full.json` 中输出 `weekly_base` 字段；前端榜单区域新增「🏆 周榜坐标」基准条，展示本周 TOP1 剧名、热度与题材 |
| 2026-06-12 | **v1.8.1 API 调用优化**：Kimi 调用从 20+ 次降到 6 次以内 |
| 2026-06-12 | `enrich_node`：删除循环 Kimi 搜索，改为先爬红果详情页 + 批量 DeepSeek 补充 |
| 2026-06-12 | `search_node`：删除标签搜索和剧目详情搜索，只保留 1 次行业数据搜索 |
| 2026-06-12 | `actor_ranking_node`：从榜单数据提取演员统计，无需 Kimi 搜索 |
| 2026-06-12 | 新增红果官网直爬模块，获取 504 部短剧基础数据（TOP100 用于榜单，TOP20 补充详情）|
| 2026-06-12 | `search_node` 重构：红果直爬为主，Kimi 搜索补充行业数据 |
| 2026-06-12 | `push_node` 支持双文件存储：`latest.json`(TOP20) + `latest_full.json`(全量 100 条) |
| 2026-06-12 | H5 响应式适配：支持 PC 和移动端，榜单滚动加载（初始 20 条，点击加载更多）|
