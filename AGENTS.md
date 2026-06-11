# 短剧行业数据看板 - AGENTS规范文档

---

## 📌 版本信息

| 版本 | Tag | 日期 | 说明 |
|------|-----|------|------|
| **当前标准版本** | `v1.7.11` | 2026-06-11 | **前端卡片精简：删除4个无效卡片 + AI短剧渗透率专项搜索** |
| v1.7.10 | - | 2026-06-11 | 演员搜索逻辑优化（历史版本） |
| v1.7.7 | - | 2026-06-11 | 时间铁律强制执行（历史版本） |
| v1.7.0 | - | 2026-06-11 | 双模型协同解耦架构（历史版本） |
| v1.6.0 | - | 2026-06-11 | Cursor改进合并后的稳定版本（历史版本，不再维护） |

⚠️ **重要：v1.7.11为当前标准版本，以前的版本代码和MD文件不要再碰！**

---

## ⚠️ 重要注意事项

### v1.7.11标准版本（前端精简+AI渗透率优化）

**前端卡片精简（删除4个无效卡片）**：
- ❌ 大盘用户规模（数据无意义）
- ❌ 市场规模（数据无意义）
- ❌ 女频占比（数据无意义）
- ✅ APP月活（保留）
- ✅ AI短剧渗透率（保留，优化搜索）
- ✅ 剧集总量（保留）
- ✅ 破亿爆款剧（保留）
- ❌ 首日ROI参考（数据无意义）

**AI短剧渗透率专项搜索**：
- 第一轮：专项搜索AI短剧占比数据
- 第二轮：搜索其他行业宏观数据
- 优先使用专项搜索结果
- 兜底：榜单统计AI剧比例或默认值（15-25%）

---

### v1.7.10标准版本（双模型协同+Tier 2+演员搜索优化）

**核心架构原则**：
- **数据采集（I/O层）**：`MoonshotClient.search()` - 国内联网搜索
- **数据推理（计算层）**：`DeepSeekClient.chat()` - 稳定JSON输出

**Tier 2配额优势**：
- 并发：100
- RPM：500
- 节流时间：缩短到1秒

**数据扩充**：
- 剧榜：TOP20（从TOP10扩充）
- 演员榜：女频TOP10 + 男频TOP10

🚨 **【演员搜索优化】（v1.7.10核心改进）**：
> **多轮搜索策略**：
> - 第一轮：`短剧《{title}》主演女演员男主角`
> - 第二轮：`《{title}》短剧演员阵容DataEye红果`
> - 第三轮：`短剧 {title} 主演是谁 小红书抖音豆瓣`
> 
> **智能停止逻辑**：
> - 搜索结果包含演员关键词（演员/主演/女主/男主）→ 立即停止
> - 三轮都无结果 → 标记为"搜索无结果，请推理补充"
> 
> **推理补充规则**：
> - 女频短剧常见演员：徐艺真、马秋元、王艺瑾、白妍、赵佳等
> - 男频短剧常见演员：曾辉、何健麒、孙晨越、王道铁等

🚨 **【时间铁律】（最高优先级）**：
> 所有爬取内容必须是【当日】数据！
> 
> **双重保障**：
> 1. **搜索关键词层**：使用 `{date_str}` 动态日期，禁止硬编码年份
> 2. **推理Prompt层**：添加时间铁律提示词，丢弃往年数据
> 
> ⚠️ 禁止硬编码 "2024"、"2025" 等年份！
> ⚠️ 往年数据一律丢弃，不作为今日数据输出！

🚨 **【配置文件修正】**：
> - news_llm_cfg.json: model改为 `deepseek-chat`
> - insights_llm_cfg.json: model改为 `deepseek-chat`
> - actor_ranking_llm_cfg.json: model改为 `deepseek-chat`
> - enrich_llm_cfg.json: model改为 `deepseek-chat`
> - industry_llm_cfg.json: model保持 `moonshot-v1-32k`（使用Kimi search_json）

**工具类**：
- `MoonshotClient` (`src/tools/moonshot_api.py`): base_url=https://api.moonshot.cn/v1
- `DeepSeekClient` (`src/tools/deepseek_api.py`): base_url=https://api.deepseek.com

**节流保护**：
- 搜索间隔: `time.sleep(1)`（Tier 2配额充足）
- 429重试: 最多5次backoff重试（10/20/30/40/50秒）

⚠️ GitHub Actions环境变量：
- `MOONSHOT_API_KEY` - Kimi搜索（已配置，Tier 2付费用户）
- `DEEPSEEK_API_KEY` - DeepSeek推理（已配置）

### Coze依赖限制
**Coze Coding内部依赖无法在GitHub Actions等外部环境使用！**

以下模块只能在Coze Coding平台内部运行：
- `coze_coding_dev_sdk` - Coze内部SDK
- `coze_coding_utils` - Coze内部工具库
- `cozeloop` - Coze内部循环库
- `S3SyncStorage` - Coze内部对象存储

**GitHub Actions入口**: `src/run_github.py`（不依赖任何Coze内部模块）

### 数据文件路径
**index.html在assets目录下，数据路径必须使用相对路径：**
```javascript
let url = './data/latest.json';  // ✅ 正确
let url = './assets/data/latest.json';  // ❌ 错误
```

### Pydantic对象访问规则

- **名称**: 短剧行业数据看板
- **作者**: Bridget Yang
- **功能**: 使用Kimi (Moonshot) API自动抓取短剧行业数据，生成多维度分析报告
- **部署方式**: GitHub Actions自动运行，每日北京时间9:00执行
- **访问地址**: https://bridgetyangjie-1.github.io/Shortvideo_news/assets/index.html

---

## 数据结构规则

### 核心数据字段

| 字段 | 类型 | 说明 |
|------|------|------|
| rankings | List[DramaRanking] | 榜单TOP10短剧 |
| daily_news | List[DailyNews] | 行业快讯5条 |
| insights | List[Insight] | 行业大事件3条 |
| genre_distribution | GenreDistribution | 题材分布+标签热度 |
| actors | ActorRanking | 演员_TOP10 |
| industry | IndustryData | 行业宏观数据 |
| audience_profile | AudienceProfile | 观众画像 |

### 行业快讯规则（v1.1要求）
- **数量**: 5条
- **内容**: 100字内总结（Kimi提炼）
- **链接**: 具体原文链接（非门户网站首页）
- **类型**: data/warn/biz（数据/预警/商业）

### 行业大事件规则（v1.1.1要求）
- **内容**: 具体事件+真实数据（如"播放量暴涨45%"）
- **来源**: Kimi联网搜索实时事件
- **禁止**: 泛泛分析（如"女频剧持续领跑"）

---

## 节点清单

| 节点名 | 文件位置 | 类型 | 功能描述 | 配置文件 |
|-------|---------|------|---------|---------|
| search_node | `nodes/search_node.py` | task | Kimi联网搜索榜单+标签数据 | - |
| news_node | `nodes/news_node.py` | agent | Kimi搜索5条快讯+100字总结+原文链接 | `config/news_llm_cfg.json` |
| process_node | `nodes/process_node.py` | agent | Kimi结构化处理榜单 | `config/process_llm_cfg.json` |
| enrich_node | `nodes/enrich_node.py` | agent | **先搜后问架构** - Python层调用search获取真实资料，再喂给LLM提取演员/标签 | `config/enrich_llm_cfg.json` |
| actor_ranking_node | `nodes/actor_ranking_node.py` | agent | Kimi生成演员人气榜 | `config/actor_ranking_llm_cfg.json` |
| industry_node | `nodes/industry_node.py` | agent | Kimi联网获取行业宏观数据 | `config/industry_llm_cfg.json` |
| audience_profile_node | `nodes/audience_profile_node.py` | agent | Kimi搜索观众画像 | `config/audience_profile_llm_cfg.json` |
| genre_distribution_node | `nodes/genre_distribution_node.py` | task | 统计题材分布+标签热度 | - |
| insights_node | `nodes/insights_node.py` | agent | **先搜后问架构** - Python层调用search获取真实事件，再生成爆款归因+买量建议 | `config/insights_llm_cfg.json` |
| history_data_node | `nodes/history_data_node.py` | task | 生成历史数据和播放趋势 | - |
| push_node | `nodes/push_node.py` | task | 保存JSON数据文件 | - |

**类型说明**: task(普通节点) / agent(大模型节点)

---

## 配置文件清单

| 文件 | 用途 | 节点 |
|------|------|------|
| `config/news_llm_cfg.json` | 快讯搜索+提炼配置 | news_node |
| `config/process_llm_cfg.json` | 榜单结构化配置 | process_node |
| `config/enrich_llm_cfg.json` | 数据补充配置 | enrich_node |
| `config/actor_ranking_llm_cfg.json` | 演员榜生成配置 | actor_ranking_node |
| `config/industry_llm_cfg.json` | 行业宏观数据配置 | industry_node |
| `config/audience_profile_llm_cfg.json` | 观众画像配置 | audience_profile_node |
| `config/insights_llm_cfg.json` | 行业大事件配置 | insights_node |

---

## 已知问题与解决方案

### 数据真实性与置信度
- **现象**: Kimi搜索可能混入非短剧演员、传统影视演员或不稳定来源
- **解决**: 见 `docs/IMPROVEMENT_ROADMAP.md`，优先新增质量门禁、来源URL和置信度字段

### GitHub Pages缓存
- **现象**: 修改后网页不更新
- **解决**: Ctrl+F5强制刷新或清除浏览器缓存

### 数据对象渲染错误
- **现象**: 显示 `[object Object]`
- **原因**: 对象类型数据直接显示
- **解决**: 正确解析对象属性（如`userScale.value + userScale.unit`）

---

## GitHub Actions部署

### 环境变量配置
在GitHub仓库设置中添加Secret：
- **名称**: `MOONSHOT_API_KEY`
- **值**: 你的Kimi (Moonshot) API密钥

### Workflow文件
路径: `.github/workflows/daily_update.yml`

关键配置：
```yaml
permissions:
  contents: write  # 必须有写入权限
```

### 运行时间
- **自动触发**: 每日UTC 1:00（北京时间9:00）
- **手动触发**: workflow_dispatch

---

## 文件结构

```
├── assets/
│   ├── index.html          # 网页看板（动态加载JSON）
│   └── data/
│       ├── latest.json     # 最新数据
│       ├── history/        # 历史数据（按日期）
│       └── all_history.json # 全部历史汇总
├── config/
│   └── *_llm_cfg.json      # 大模型配置文件
├── src/
│   ├── graphs/
│   │   ├── graph.py        # 主图编排
│   │   ├── state.py        # 数据结构定义
│   │   └── nodes/          # 节点实现
│   ├── tools/
│   │   └── moonshot_api.py # Kimi (Moonshot) API工具
│   ├── utils/
│   │   └── runtime.py      # Context替代类
│   └── run_github.py       # GitHub Actions入口
├── AGENTS.md               # 本文件
└── .gitignore              # 忽略截屏图片等
```