# 短剧行业研究数据自动更新工作流

## 项目概述
- **名称**: 短剧行业研究数据自动更新工作流
- **功能**: 自动抓取短剧行业热榜数据，生成多维度分析报告并推送

---

## 节点清单

| 节点名 | 文件位置 | 类型 | 功能描述 | 分支逻辑 | 配置文件 |
|-------|---------|------|---------|---------|---------|
| search_node | `nodes/search_node.py` | task | 搜索短剧榜单数据 | - | - |
| news_node | `nodes/news_node.py` | agent | 搜索并提炼行业快讯(Tier1+Tier2) | - | `config/news_llm_cfg.json` |
| process_node | `nodes/process_node.py` | agent | LLM结构化处理榜单(Tier1) | - | `config/process_llm_cfg.json` |
| enrich_node | `nodes/enrich_node.py` | agent | LLM补充演员/标签/描述(Tier2) | - | `config/enrich_llm_cfg.json` |
| actor_ranking_node | `nodes/actor_ranking_node.py` | agent | LLM生成演员人气榜 | - | `config/actor_ranking_llm_cfg.json` |
| industry_node | `nodes/industry_node.py` | agent | LLM获取行业宏观数据(Tier1+Tier2) | - | `config/industry_llm_cfg.json` |
| audience_profile_node | `nodes/audience_profile_node.py` | agent | LLM生成观众画像数据 | - | `config/audience_profile_llm_cfg.json` |
| genre_distribution_node | `nodes/genre_distribution_node.py` | task | 统计题材分布 | - | - |
| insights_node | `nodes/insights_node.py` | agent | 异动触发式点评(最多2条,Tier3) | - | `config/insights_llm_cfg.json` |
| history_data_node | `nodes/history_data_node.py` | task | 生成周榜历史和播放趋势 | - | - |
| push_node | `nodes/push_node.py` | task | 生成HTML+JSON并存储历史数据 | - | - |

**类型说明**: task(普通节点) / agent(大模型节点) / condition(条件分支) / looparray(列表循环) / loopcond(条件循环)

**Tier分层**:
- Tier1(确切事实): 搜索爬取数据,不经LLM篡改
- Tier2(AI搜补): DeepSeek联网搜索补全缺失字段
- Tier3(AI推理): 基于数据推理生成洞察和建议

---

## 子图清单

无子图

---

## 技能使用

- `search_node` 使用 **web-search** 技能搜索公开数据源
- `news_node` 使用 **web-search** 技能搜索行业快讯 + **llm** 技能提炼摘要
- `process_node` 使用 **llm** 技能进行结构化处理(Tier1)
- `enrich_node` 使用 **llm** 技能补充数据(Tier2)
- `actor_ranking_node` 使用 **llm** 技能生成演员榜单
- `industry_node` 使用 **llm** 技能分析行业数据(Tier1+Tier2)
- `audience_profile_node` 使用 **llm** 技能生成观众画像
- `insights_node` 使用 **llm** 技能生成异动点评(Tier3,最多2条)

---

## 数据流图

```
GraphInput(data_date)
    ↓
search_node → 搜索榜单数据
    ↓
process_node → 结构化处理
    ↓
enrich_node → 补充演员/标签/描述
    ↓
┌───────────────────────────────────────┐
│ actor_ranking_node → 演员榜单          │
│ industry_node → 行业数据               │
│ audience_profile_node → 观众画像       │
│ genre_distribution_node → 题材分布     │
│ history_data_node → 周榜历史/播放趋势  │
└───────────────────────────────────────┘
    ↓
┌───────────────────────────────────────┐
│ insights_node → 行业洞察               │
│ innovations_node → 创新点              │
└───────────────────────────────────────┘
    ↓
push_node → 推送数据
    ↓
GraphOutput(完整数据)
```

---

## 输出数据结构

| 字段 | 类型 | 描述 |
|-----|------|------|
| success | bool | 是否成功 |
| generated_at | str | 生成时间 |
| data_date | str | 数据日期 |
| industry | IndustryData | 行业数据（用户规模、市场规模等） |
| rankings | List[DramaRanking] | TOP10榜单数据 |
| actors | ActorsData | 演员榜单（女频TOP10 + 男频TOP10） |
| platform | PlatformData | 平台数据（APP月活等） |
| audience_profile | AudienceProfile | 观众画像（性别、年龄、地域分布） |
| genre_distribution | GenreDistribution | 题材分布统计 |
| weekly_rankings | List[WeeklyRankingItem] | 周榜历史 |
| play_trend | PlayTrend | 播放量趋势 |
| insights | List[Insight] | 5条行业洞察 |
| innovations | List[Innovation] | 5条创新点 |
| quality_score | float | 数据质量分数 |
