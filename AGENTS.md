# 短剧行业数据看板 - Agent 工作规则

> 本文是给 AI 编码代理阅读的当前有效规则。历史方案、过期部署说明和一次性项目总结不要放入本文件。
> 项目对外介绍、运行方式请见 `README.md`，改进计划请见 `docs/ROADMAP.md`。

## 1. 项目概述

这是一个自动化的**短剧行业数据看板**系统。每天北京时间 9:00（UTC 1:00）由 GitHub Actions 触发，爬取红果官网榜单、补充演员与厂牌信息、生成行业快讯与洞察，最终输出静态 JSON 数据，托管在 GitHub Pages 上供前端展示。

- **项目名称**：`shortvideo-news`
- **当前版本**：`v1.9.0`
- **在线地址**：https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html
- **数据入口**：`assets/data/latest.json`（TOP20 展示）、`assets/data/latest_full.json`（Full100 归档）
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
│   ├── history_data.json                # 播放趋势与周榜历史
│   └── data/
│       ├── latest.json                  # TOP20 展示数据
│       ├── latest_full.json             # 全量榜单（可达 100 条）
│       ├── all_history.json             # 近 30 天历史索引
│       └── history/YYYY-MM-DD.json      # 按日归档
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
│   │   ├── state.py                     # 全部 Pydantic 状态模型
│   │   ├── ranking_quality.py           # TOP20 榜单数量质量门禁
│   │   └── nodes/                       # 11 个处理节点
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
    └──→ process_node─┘
              ↓
        enrich_node
              ↓
        actor_ranking_node
              ├──→ industry_node ──┐
              └──→ audience_profile_node─┘
                            ↓
                    genre_distribution_node
                            ↓
                       insights_node
                            ↓
                       history_data_node
                            ↓
                         push_node → END
```

- `news_node` 与 `process_node` 在 `search_node` 后并行。
- `industry_node` 与 `audience_profile_node` 在 `actor_ranking_node` 后并行。
- `push_node` 前由 `should_push_data` 判断：失败或质量分低于 60 分则跳过推送。

## 6. 代码组织

### 6.1 `src/graphs/nodes/` 节点层

| 节点 | 文件 | 主要功能 | 是否依赖 LLM |
|---|---|---|---|
| `search_node` | `search_node.py` | 红果官网直爬 + DataEye 交叉验证 + 1 次 Kimi 行业宏观搜索 | 否（爬虫）+ Kimi 1 次 |
| `process_node` | `process_node.py` | 优先处理红果数据；无数据时用 Kimi 提取榜单 | 是（Kimi，备选） |
| `enrich_node` | `enrich_node.py` | 本地缓存 → 红果详情页爬虫 → Kimi 批量补充 → DeepSeek 生成完整 JSON | 是（DeepSeek/Kimi） |
| `actor_ranking_node` | `actor_ranking_node.py` | 从 enriched_rankings 统计演员频次，生成女频/男频 TOP10 | 否 / DeepSeek 兜底 |
| `industry_node` | `industry_node.py` | 搜索行业宏观数据，输出 IndustryData + PlatformData | 是（Kimi） |
| `audience_profile_node` | `audience_profile_node.py` | 基于当日榜单反推受众画像 | 是（DeepSeek） |
| `genre_distribution_node` | `genre_distribution_node.py` | 本地统计 genre/tags/core_trope 标签频次 | 否 |
| `insights_node` | `insights_node.py` | Kimi 搜索行业事件 → DeepSeek 生成 2 条商业洞察 | 是（Kimi+DeepSeek） |
| `news_node` | `news_node.py` | Kimi 搜索 3 组新闻 → DeepSeek 生成最多 6 条快讯 | 是（Kimi+DeepSeek） |
| `history_data_node` | `history_data_node.py` | 生成播放趋势、周榜历史、排名变化 | 否 |
| `push_node` | `push_node.py` | 保存 latest.json、latest_full.json、历史归档、all_history.json | 否 |

### 6.2 `src/tools/` 工具层

| 工具 | 文件 | 作用 |
|---|---|---|
| `HongguoCrawler` | `hongguo_crawler.py` | 爬取 `novelquickapp.com` 首页 `_ROUTER_DATA`，获取最多 100 条榜单 |
| `DataEyeCrawler` | `dataeye_crawler.py` | 爬取 DataEye 热力榜，用于交叉验证 |
| `CacheDB` | `cache_db.py` | SQLite 本地缓存，7 天有效期，存储演员/工作室/标签 |
| `TagNormalizer` | `tag_normalizer.py` | 标签同义词映射、题材分类（female/male/neutral） |
| `MoonshotClient` | `moonshot_api.py` | Kimi 客户端：chat、search、JSON 提取、429 退避、API 预算熔断 |
| `DeepSeekClient` | `deepseek_api.py` | DeepSeek 客户端：chat 接口 |

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

1. **search_node**：抓取红果官网 100 条 + DataEye 30 条交叉验证，生成融合榜单；再用 Kimi 搜索 1 次行业宏观数据。
2. **news_node**：并行运行，Kimi 搜索 3 组新闻 → DeepSeek 生成 ≤6 条快讯。
3. **process_node**：优先解析红果直接爬取数据，转换为标准榜单；无数据时用 Kimi 从搜索结果提取。
4. **enrich_node**：对前 20 条，先查 SQLite 缓存，再爬红果详情页，Kimi 批量搜索补充，最后 DeepSeek 生成完整 JSON（含 emotional_analysis）。
5. **actor_ranking_node**：从 enriched_rankings 统计演员出现频次，生成女频/男频 TOP10；不足时用 DeepSeek 兜底。
6. **industry_node**：用 Kimi 搜索行业宏观数据，结合榜单 AI/女男频比例，输出 IndustryData。
7. **audience_profile_node**：用 DeepSeek 基于当日榜单反推受众画像。
8. **genre_distribution_node**：本地统计标签频次，输出 hot_tags。
9. **insights_node**：Kimi 搜索行业事件 → DeepSeek 生成 2 条商业洞察。
10. **history_data_node**：更新 `assets/history_data.json`，生成播放趋势、周榜、排名变化。
11. **push_node**：输出 `latest.json`（TOP20）、`latest_full.json`（全量）、`assets/data/history/YYYY-MM-DD.json`、`assets/data/all_history.json`。

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

### 8.3 前端

- `assets/index.html` 在 `assets/` 目录下，数据路径必须使用相对路径：

  ```javascript
  fetch('./data/latest.json')
  ```

- Python 节点只输出 JSON，不拼接或覆盖 HTML。
- 前端渲染对象字段时必须展开属性，避免显示 `[object Object]`。
- 不要把指标数据写死进 HTML。

## 9. 测试说明

- **测试文件**：`tests/test_ranking_quality.py`
- **框架**：`unittest`
- **测试内容**：
  1. `test_uses_recent_history_to_reach_top20`：用历史数据补齐到 20 条。
  2. `test_raises_when_sources_cannot_reach_top20`：来源不足时抛出 `RankingCountError`。

运行：

```bash
python -m unittest tests.test_ranking_quality
```

新增节点或修改状态模型时，应补充对应单元测试。测试数据使用临时目录，不要依赖真实 API key。

## 10. 数据规则与质量门禁

### 10.1 数据采集优先级

1. **红果官网直接爬取**：`tools/hongguo_crawler.py` 直接抓取 `novelquickapp.com` 首页榜单，获取 100 条实时数据。
2. **Kimi 搜索补充**：行业宏观数据、标签分布、演员信息等。
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
| `daily_news` | `List[DailyNews]` | 6 条快讯 |
| `insights` | `List[Insight]` | 具体行业事件，必须含真实数据 |
| `genre_distribution` | `GenreDistribution` | 题材分布和标签热度 |
| `actors` | `ActorRanking` | 女频/男频演员榜 |
| `industry` | `IndustryData` | APP 月活、AI 短剧渗透率、剧集总量等 |
| `audience_profile` | `AudienceProfile` | 性别、年龄、地域画像 |

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

## 14. 开发约定

- **入口选择**：本地完整运行使用 `src/run_github.py`；Coze 平台调试使用 `src/main.py`。
- **路径约定**：所有基于项目根目录的路径通过 `COZE_WORKSPACE_PATH` 解析，不要写死绝对路径。
- **新增节点**：必须在 `src/graphs/graph.py` 中注册，并在 `src/graphs/state.py` 中定义输入输出模型。
- **新增 LLM 调用**：优先复用 `MoonshotClient`/`DeepSeekClient`，注意 API 预算熔断逻辑。
- **修改 AGENTS.md 中提到的文件/流程后，必须同步更新本文件**。
- 不再新增大型历史总结类 Markdown；旧方案如需保留，优先压缩成 README 或 ROADMAP 的一小节。

## 15. 近期变更

| 日期 | 改动 |
|------|------|
| 2026-06-12 | **v1.9.0 第二阶段优化**：本地缓存 + 多源验证 + 排名趋势 |
| 2026-06-12 | 新增 `tools/cache_db.py`：本地 SQLite 缓存，7 天内有效，避免重复搜索 |
| 2026-06-12 | 新增 `tools/tag_normalizer.py`：标签标准化与题材分类 |
| 2026-06-12 | 新增 `tools/dataeye_crawler.py`：DataEye 榜单爬取，交叉验证红果数据 |
| 2026-06-12 | `state.py` 新增字段：`confidence_score`、`data_source`、`rank_change`、`is_new` |
| 2026-06-12 | `search_node`：红果 + DataEye 双源融合，置信度加权 |
| 2026-06-12 | `enrich_node`：优先本地缓存，缓存 miss 时批量补充 |
| 2026-06-12 | `history_data_node`：计算排名变化（new/up/down/same） |
| 2026-06-12 | `push_node`：输出 statistics/trends/anomalies 统计信息 |
| 2026-06-12 | **v1.8.1 API 调用优化**：Kimi 调用从 20+ 次降到 6 次以内 |
| 2026-06-12 | `enrich_node`：删除循环 Kimi 搜索，改为先爬红果详情页 + 批量 DeepSeek 补充 |
| 2026-06-12 | `search_node`：删除标签搜索和剧目详情搜索，只保留 1 次行业数据搜索 |
| 2026-06-12 | `actor_ranking_node`：从榜单数据提取演员统计，无需 Kimi 搜索 |
| 2026-06-12 | 新增红果官网直爬模块，获取 504 部短剧基础数据（TOP100 用于榜单，TOP20 补充详情）|
| 2026-06-12 | `search_node` 重构：红果直爬为主，Kimi 搜索补充行业数据 |
| 2026-06-12 | `push_node` 支持双文件存储：`latest.json`(TOP20) + `latest_full.json`(全量 100 条) |
| 2026-06-12 | H5 响应式适配：支持 PC 和移动端，榜单滚动加载（初始 20 条，点击加载更多）|
