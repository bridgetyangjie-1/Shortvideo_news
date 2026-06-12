# 短剧行业数据看板 - Agent 工作规则

本文只保留当前有效规则，避免自动上下文过长。历史方案、过期部署说明和一次性项目总结不要放入本文件。

## 当前基线

- 当前标准版本：`v1.8.0`
- 访问地址：https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html
- GitHub Actions 入口：`src/run_github.py`
- 前端入口：`assets/index.html`
- 数据入口：`assets/data/latest.json`（TOP20展示）、`assets/data/latest_full.json`（Full100归档）

## 架构边界

| 层级 | 组件 | 职责 |
|---|---|---|
| 数据采集 | `HongguoCrawler` | 直接爬取红果官网实时榜单（优先） |
| 数据采集 | `MoonshotClient.search()` | Kimi/Moonshot 联网搜索补充行业数据 |
| 数据推理 | `DeepSeekClient.chat()` | 稳定 JSON 推理与结构化输出 |
| 编排 | `src/graphs/graph.py` | 串联各数据节点 |
| 发布 | `src/graphs/nodes/push_node.py` | 输出TOP20+Full100双JSON文件 |
| 展示 | `assets/index.html` | 静态页面动态读取JSON |

GitHub Actions 运行时不要依赖 Coze 内部 SDK。`src/main.py` 和 Coze 兼容代码只用于 Coze Coding 场景，外部自动化以 `src/run_github.py` 为准。

## 数据采集优先级

1. **红果官网直接爬取**：`tools/hongguo_crawler.py` 直接抓取 novelquickapp.com 首页榜单，获取100条实时数据
2. **Kimi搜索补充**：行业宏观数据、标签分布、演员信息等
3. **历史数据兜底**：近7天归档数据用于补齐不足8条的榜单

## 硬性数据规则

### 时间铁律

- 所有搜索关键词必须使用当前运行日期或 `state.data_date` 动态生成。
- 禁止硬编码年份作为“今日数据”条件。
- 今日数据不足时，行业快讯可补充近 7 天重要动态，但要避免把往年数据当作今日数据。

### 行业快讯

- `daily_news` 必须返回 5 条。
- 每条必须包含 `insight` 字段，约 100 字，覆盖行业影响、趋势判断、商业机会或风险。
- 每条必须包含具体 `source_url`，避免只给门户首页。
- 类型限定为数据、预警、商业等清晰分类。

### 榜单与演员

- 剧集榜单目标为 TOP20。
- 前端“榜单 TOP8”必须严格显示 8 条；`rankings` 少于 8 条时必须补齐或拒绝发布，禁止直接覆盖 `latest.json`。
- 演员榜为女频 TOP10 + 男频 TOP10。
- 演员搜索优先多轮检索：
  1. `短剧《{title}》主演女演员男主角`
  2. `《{title}》短剧演员阵容DataEye红果`
  3. `短剧 {title} 主演是谁 小红书抖音豆瓣`
- 演员字段不要填“未知”；搜索失败时按女频/男频常见短剧演员进行合理推理补充。

### JSON 与前端

- Pydantic 对象使用属性访问，如 `obj.field_name`，不要假设可用 `.get()`。
- `assets/index.html` 在 `assets/` 目录下，数据路径必须使用：

```javascript
fetch('./data/latest.json')
```

- Python 节点只输出 JSON，不拼接或覆盖 HTML。
- 前端渲染对象字段时必须展开属性，避免显示 `[object Object]`。

## 核心数据结构

| 字段 | 类型 | 要求 |
|---|---|---|
| `rankings` | `List[DramaRanking]` | TOP20 短剧榜单 |
| `daily_news` | `List[DailyNews]` | 5 条快讯，每条250-350字四段式摘要 |
| `insights` | `List[Insight]` | 具体行业事件，必须含真实数据 |
| `genre_distribution` | `GenreDistribution` | 题材分布和标签热度 |
| `actors` | `ActorRanking` | 女频/男频演员榜 |
| `industry` | `IndustryData` | APP 月活、AI 短剧渗透率、剧集总量等 |
| `audience_profile` | `AudienceProfile` | 性别、年龄、地域画像 |

## 节点清单

| 节点 | 文件 | 作用 |
|---|---|---|
| `search_node` | `src/graphs/nodes/search_node.py` | 直接爬取红果官网 + Kimi搜索补充 |
| `process_node` | `src/graphs/nodes/process_node.py` | 优先处理红果数据，无数据时用Kimi结果 |
| `enrich_node` | `src/graphs/nodes/enrich_node.py` | 搜索并补全演员、厂牌、标签 |
| `industry_node` | `src/graphs/nodes/industry_node.py` | 行业宏观数据 |
| `audience_profile_node` | `src/graphs/nodes/audience_profile_node.py` | 观众画像 |
| `genre_distribution_node` | `src/graphs/nodes/genre_distribution_node.py` | 题材分布统计 |
| `actor_ranking_node` | `src/graphs/nodes/actor_ranking_node.py` | 演员热度榜 |
| `insights_node` | `src/graphs/nodes/insights_node.py` | 行业大事件 |
| `news_node` | `src/graphs/nodes/news_node.py` | 行业快讯 |
| `history_data_node` | `src/graphs/nodes/history_data_node.py` | 历史数据 |
| `push_node` | `src/graphs/nodes/push_node.py` | 保存TOP20+Full100双JSON |

## 工具类

| 工具 | 文件 | 作用 |
|---|---|---|
| `HongguoCrawler` | `src/tools/hongguo_crawler.py` | 直接爬取红果官网榜单 |
| `MoonshotClient` | `src/tools/moonshot_api.py` | Kimi联网搜索 |
| `DeepSeekClient` | `src/tools/deepseek_api.py` | DeepSeek JSON推理 |

## 模型配置约定

| 配置 | 当前模型 |
|---|---|
| `config/news_llm_cfg.json` | `deepseek-chat` |
| `config/insights_llm_cfg.json` | `deepseek-chat` |
| `config/actor_ranking_llm_cfg.json` | `deepseek-chat` |
| `config/enrich_llm_cfg.json` | `deepseek-chat` |
| `config/industry_llm_cfg.json` | `moonshot-v1-32k` |

`MOONSHOT_API_KEY` 和 `DEEPSEEK_API_KEY` 是 GitHub Actions 必需 secrets。

## 文档维护规则

- 自动上下文规则只放在本文件，保持短而当前。
- 项目介绍、运行方式和文档入口放在 `README.md`。
- 后续改进计划放在 `docs/ROADMAP.md`。
- 不再新增大型历史总结类 MD；旧方案如需保留，优先压缩成 README 或 ROADMAP 的一小节。

## 近期变更

| 日期 | 改动 |
|------|------|
| 2026-06-12 | 新增红果官网直爬模块，获取504部短剧基础数据（TOP100用于榜单，TOP20补充详情）|
| 2026-06-12 | search_node重构：红果直爬为主，Kimi搜索补充行业数据 |
| 2026-06-12 | push_node支持双文件存储：latest.json(TOP20) + latest_full.json(全量100条) |
| 2026-06-12 | H5响应式适配：支持PC和移动端，榜单滚动加载（初始20条，点击加载更多）|
