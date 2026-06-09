# 短剧行业研究数据自动更新工作流

## ⚠️ 重要注意事项

**Coze Coding内部依赖无法在GitHub Actions等外部环境使用！**

以下模块只能在Coze Coding平台内部运行：
- `coze_coding_dev_sdk` - Coze内部SDK
- `coze_coding_utils` - Coze内部工具库
- `cozeloop` - Coze内部循环库
- `S3SyncStorage` - Coze内部对象存储

**GitHub Actions入口**: `src/run_github.py`（不依赖任何Coze内部模块）

## 项目概述
- **名称**: 短剧行业研究数据自动更新工作流
- **功能**: 使用DeepSeek API自动抓取短剧行业热榜数据，生成多维度分析报告
- **部署方式**: GitHub Actions自动运行，每日北京时间9:00执行

---

## 节点清单

| 节点名 | 文件位置 | 类型 | 功能描述 | 分支逻辑 | 配置文件 |
|-------|---------|------|---------|---------|---------|
| search_node | `nodes/search_node.py` | task | DeepSeek联网搜索短剧榜单数据 | - | - |
| news_node | `nodes/news_node.py` | agent | DeepSeek联网搜索并提炼行业快讯 | - | `config/news_llm_cfg.json` |
| process_node | `nodes/process_node.py` | agent | DeepSeek结构化处理榜单(Tier1) | - | `config/process_llm_cfg.json` |
| enrich_node | `nodes/enrich_node.py` | agent | DeepSeek补充演员/标签/描述(Tier2) | - | `config/enrich_llm_cfg.json` |
| actor_ranking_node | `nodes/actor_ranking_node.py` | agent | DeepSeek生成演员人气榜 | - | `config/actor_ranking_llm_cfg.json` |
| industry_node | `nodes/industry_node.py` | agent | DeepSeek联网获取行业宏观数据 | - | `config/industry_llm_cfg.json` |
| audience_profile_node | `nodes/audience_profile_node.py` | agent | DeepSeek联网搜索观众画像数据 | - | `config/audience_profile_llm_cfg.json` |
| genre_distribution_node | `nodes/genre_distribution_node.py` | task | 统计题材分布 | - | - |
| insights_node | `nodes/insights_node.py` | agent | DeepSeek生成行业洞察(Tier3) | - | `config/insights_llm_cfg.json` |
| history_data_node | `nodes/history_data_node.py` | task | 生成周榜历史和播放趋势 | - | - |
| push_node | `nodes/push_node.py` | task | 生成JSON、保存本地文件 | - | - |

**类型说明**: task(普通节点) / agent(大模型节点) / condition(条件分支) / looparray(列表循环) / loopcond(条件循环)

**Tier分层**:
- Tier1(确切事实): DeepSeek联网搜索数据,保持原始准确性
- Tier2(AI搜补): DeepSeek联网搜索补全缺失字段
- Tier3(AI推理): 基于数据推理生成洞察和建议

---

## 子图清单

无子图

---

## 技能使用

**⚠️ 重要变更**: 所有节点已迁移至使用 **DeepSeek API**，不再依赖Coze内部SDK。

| 节点 | API调用类型 | 说明 |
|------|------------|------|
| search_node | DeepSeek联网搜索 | 搜索短剧榜单数据 |
| news_node | DeepSeek联网搜索 + 对话 | 搜索快讯并提炼摘要 |
| process_node | DeepSeek对话 | 结构化处理榜单数据 |
| enrich_node | DeepSeek对话 | 补充演员/标签/描述 |
| actor_ranking_node | DeepSeek对话 | 生成演员人气榜 |
| industry_node | DeepSeek联网搜索 + 对话 | 获取行业宏观数据 |
| audience_profile_node | DeepSeek联网搜索 | 搜索观众画像数据 |
| insights_node | DeepSeek对话 | 生成行业洞察 |

---

## GitHub Actions部署

### 环境变量配置
在GitHub仓库设置中添加Secret：
- **名称**: `DEEPSEEK_API_KEY`
- **值**: 你的DeepSeek API密钥

### 工作流程
1. 每日北京时间9:00自动触发
2. 运行Python工作流（使用DeepSeek API）
3. 生成数据文件到 `assets/data/`
4. 自动提交并推送到仓库

---

## 工具类

| 工具 | 文件位置 | 功能 |
|------|---------|------|
| DeepSeekClient | `tools/deepseek_api.py` | DeepSeek API封装（支持对话和联网搜索） |

---

## GitHub Actions 自动运行

**重要变更**: 项目已完全迁移至 **DeepSeek API**，可以在GitHub Actions环境中直接运行。

### 工作流程
1. 每日北京时间9:00自动触发
2. GitHub Actions运行Python工作流（使用DeepSeek API）
3. DeepSeek联网搜索获取实时数据
4. 生成JSON数据文件到 `assets/data/latest.json`
5. 更新HTML兜底数据
6. 自动提交并推送到仓库

### 环境变量配置
在GitHub仓库设置Secret：
- **名称**: `DEEPSEEK_API_KEY`
- **值**: 你的DeepSeek API密钥

### 数据同步方案（可选）
如需从Coze Coding环境同步数据：
- `storage_key`: `short-drama/latest-{日期}.json`
- `storage_url`: 对象存储签名URL（30天有效）
   - 可使用固定Key生成长期有效的签名URL

2. GitHub Actions会自动：
   - 每天UTC 1:00（北京时间9:00）尝试同步
   - 或手动触发workflow_dispatch

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
