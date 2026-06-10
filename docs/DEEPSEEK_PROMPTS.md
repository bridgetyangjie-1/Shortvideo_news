# DeepSeek API 调用说明文档

> 本文档记录所有使用 DeepSeek API 进行数据爬取/搜索的节点，包括爬取目的、搜索内容、Prompt 配置等。

---

## 目录

1. [search_node - 数据抓取节点](#1-search_node---数据抓取节点)
2. [news_node - 行业快讯节点](#2-news_node---行业快讯节点)
3. [enrich_node - 数据补全节点](#3-enrich_node---数据补全节点)
4. [actor_ranking_node - 演员榜单节点](#4-actor_ranking_node---演员榜单节点)
5. [industry_node - 行业大盘节点](#5-industry_node---行业大盘节点)
6. [insights_node - 行业大事件节点](#6-insights_node---行业大事件节点)
7. [audience_profile_node - 观众画像节点](#7-audience_profile_node---观众画像节点)

---

## 1. search_node - 数据抓取节点

### 为什么爬取
获取短剧行业的基础数据，包括：
-热播短剧TOP10榜单（剧名、播放量、平台）
- 行业宏观数据（用户规模、市场规模）
- 重点平台数据（红果、抖音等）
- 演员人气数据
- 红果平台标签数据

### 搜索内容

#### 主数据搜索 Prompt
```
请搜索互联网，获取最新的短剧行业数据。重点关注以下数据源：

1. DataEye短剧热力榜 - 热播短剧排名、播放量数据
2. 云合数据短剧报告 - 有效播放、市占率分析
3. 红果短剧周榜 - 红果平台热门短剧排名
4. QuestMobile短剧用户分析 - 用户规模、画像数据
5. 其他公开的短剧榜单数据源

日期参考：{data_date}

请返回：
1. 今日/本周热播短剧TOP10榜单（包含剧名、播放量、平台）
2. 行业宏观数据（用户规模、市场规模、增长趋势）
3. 重点平台数据（红果、抖音等平台的MAU、活跃度）
4. 最新演员人气数据

格式要求：
- 返回具体的数值和事实
- 尝试标注数据来源
- 如果某些数据无法获取，标注"暂无数据"
```

#### 红果标签搜索 Prompt
```
请搜索红果短剧平台的"最热"分类页面数据。

重点关注：
1. 热门短剧的标签信息（如都市、甜宠、重生、穿越、马甲、打脸等）
2. 各标签对应的短剧数量和播放量热度
3. 红果平台的标签分类体系：
   - 背景标签：现代、都市、古代、乡村、年代、架空、职场、民国、校园等
   - 主题标签：甜宠、复仇、玄幻、仙侠、悬疑、喜剧、女性成长等
   - 设定标签：重生、穿越、马甲、打脸虐渣、大女主、先婚后爱、系统等

请返回具体的标签统计数据，格式如下：
{
  "background_tags": [{"name": "现代", "count": 18}, ...],
  "theme_tags": [{"name": "甜宠", "count": 12}, ...],
  "setting_tags": [{"name": "重生", "count": 15}, ...]
}
```

### System Prompt
```
你是一个专业的数据分析师，擅长从互联网搜索并整理行业数据。
请搜索最新的公开数据源，返回具体的事实和数值。
```

### 配置参数
| 参数 | 值 |
|------|-----|
| temperature | 0.3 |
| max_tokens | 8192 |

---

## 2. news_node - 行业快讯节点

### 为什么爬取
提炼短剧行业每日重要新闻，生成5条快讯：
- 每条100字内总结
- 附上具体原文链接（非门户网站首页）

### 搜索内容

#### 搜索关键词列表
```python
search_queries = [
    "短剧行业 最新新闻 2024 2025",
    "DataEye 短剧热度榜 最新",
    "广电总局 短剧新规 政策",
    "抖音短剧 分成比例 最新政策",
    "短剧MCN 九州 点众 最新动态"
]
```

#### System Prompt (SP)
```
你是短剧行业情报提炼引擎。你的任务是从互联网搜索结果中提炼5条最重要的行业新闻。

🚨【核心铁律】
1. 必须分类为：【预警】（政策收紧/风控/下架）、【商业】（融资/大厂动作/新规）、【数据】（大盘/爆款/战报）。
2. 每条content不超过100字，只陈述客观事实（谁、做了什么、影响什么）。
3. 每条必须有source_url，必须是可访问的原文链接URL。
4. 必须输出合法JSON数组。

# 输出格式
[{"type": "预警/商业/数据", "icon": "emoji", "title": "标题", "content": "内容缩写", "source_url": "原文链接"}]
```

#### User Prompt (UP)
```
【今日日期】：{{date}}

请搜索短剧行业最近一周最重要的新闻，输出5条JSON格式的行业快讯（每条必须包含source_url原文链接）。
```

### 配置文件
| 参数 | 值 |
|------|-----|
| model | deepseek-chat |
| temperature | 0.2 |
| max_completion_tokens | 2000 |

---

## 3. enrich_node - 数据补全节点

### 为什么爬取
基础榜单数据通常缺少：
- 制作厂牌信息（九州、点众、麦芽等）
- 核心爽点标签（真假千金、打脸绿茶、战神赘婿等）
- 集数信息（通常60-100集）

### System Prompt (SP)
```
你是短剧生态的骨灰级网文拆解专家。你的任务是根据基础榜单，补全并深挖每部剧的隐性商业信息。

🚨【规则】
1. 必须推测或利用你的知识库提取出『production_house』(制作厂牌，如九州、点众、麦芽，若实在未知填'未知厂牌')。
2. 必须将宽泛的题材细化为 2-3个『core_trope』(核心爽点标签数组，如 ["真假千金", "打脸绿茶", "战神赘婿"])。
3. 推断『episodes_count』(总集数，通常在 60-100 之间)。
4. 必须输出完整的 JSON 数组，保持与输入相同的顺序。
```

#### User Prompt (UP)
```
【数据日期】：{{data_date}}
【基础榜单数据】：
{{basic_rankings}}

请补全缺失字段（特别是 production_house 和 core_trope），并输出完整的 JSON 数组：
```

### 配置文件
| 参数 | 值 |
|------|-----|
| model | deepseek-chat |
| temperature | 0.3 |
| max_completion_tokens | 2000 |

---

## 4. actor_ranking_node - 演员榜单节点

### 为什么爬取
根据榜单数据中的演员信息，生成演员人气排行榜：
- 女频演员TOP5
- 男频演员TOP5
- 人气值（800-999）

### System Prompt (SP)
```
你是短剧生态数据专家。任务是根据大盘榜单数据，统计并生成『女频演员』和『男频演员』的人力热度榜 TOP5。

🚨【规则】
1. 仔细扫描传入榜单的 female_lead 和 male_lead 字段。
2. 根据其代表作在榜单中的名次和播放量，合理赋予一个 `popularity` (800-999 的整数)。
3. 严格输出 JSON：{"female": [{"rank":1, "name":"...", "works":"...", "popularity": 985}], "male": [...]}
```

#### User Prompt (UP)
```
【今日大盘榜单】：
{{rankings}}

请根据以上作品名单，提炼出男/女演员排行榜，输出 JSON：
```

### 配置文件
| 参数 | 值 |
|------|-----|
| model | deepseek-chat |
| temperature | 0.2 |
| max_completion_tokens | 1500 |

---

## 5. industry_node - 行业大盘节点

### 为什么爬取
提取短剧行业宏观指标：
- 用户规模（亿）
- 市场规模（亿）
- 短剧数量（万）
- 爆款数量
- APP MAU
- AI短剧比例
- 女频比例

### System Prompt (SP)
```
你是一个严谨的行业分析师，负责从最新的搜索数据中抽取短剧大盘核心指标。
如果搜索结果中未明确说明，请结合上下文给出合理的【预估值】，绝不允许留空。
必须输出严格的 JSON 结构。
```

#### User Prompt (UP)
```
【搜索参考资料】：
{{search_results}}
【榜单初步测算的AI比例】：{{ai_ratio}}%
【女频比例】：{{female_ratio}}%

请填充并返回以下 JSON 结构：
{
  "user_scale": "x.xx亿", 
  "market_size": "xxxx亿+", 
  "drama_count": "xx万+", 
  "billion_dramas": 20, 
  "app_mau": "x.xx亿", 
  "ai_ratio": {{ai_ratio}}, 
  "female_ratio": {{female_ratio}}, 
  "platform_apps": [{"name": "红果免费短剧", "share": 45}]
}
```

### 配置文件
| 参数 | 值 |
|------|-----|
| model | deepseek-chat |
| temperature | 0.2 |
| max_completion_tokens | 1000 |

---

## 6. insights_node - 行业大事件节点

### 为什么爬取
从榜单和行业数据中提炼具体的「大事件」：
- 播放量暴涨（环比增长超30%）
- 新剧爆发（首日播放破千万）
- 厂牌动向（连续3部上榜）
- 商业事件（融资、并购、新规）
- 技术突破（AI短剧创新高）

### System Prompt (SP)
```
你是短剧行业情报官，负责从榜单和行业数据中提炼具体的「大事件」。

🚨【核心铁律】
1. 必须是具体事件，禁止泛泛分析（如"女频主导"、"市场增长"等废话）
2. 必须包含具体数据（剧目名、播放量、变化幅度、厂牌名等）
3. 每条事件必须指出：谁 + 做了什么 + 数据变化 + 影响什么
4. 如果没有明显大事件，输出"大盘平稳"即可

# 大事件类型（优先级）
- 📈 播放量暴涨：某剧播放量环比增长超过30%
- 🔥 新剧爆发：新上榜剧目首日播放破千万
- 🏭 厂牌动向：某厂牌连续3部上榜，或推出新爆款
- 💰 商业事件：融资、并购、平台新规、分成政策变化
- 🤖 技术突破：AI短剧播放量创新高，新工具上线

# 输出格式（严格JSON数组）
[{"icon": "emoji", "title": "事件标题（10字）", "content": "具体描述（含数据，80字以内）"}]
```

#### User Prompt (UP)
```
【日期】：{{data_date}}
【今日榜单TOP8】：
{{rankings}}
【行业大盘】：
{{industry}}

请输出2-3条具体的行业大事件（必须含数据，禁止泛泛分析）：
```

### 配置文件
| 参数 | 值 |
|------|-----|
| model | deepseek-chat |
| temperature | 0.1 |
| max_completion_tokens | 2000 |

---

## 7. audience_profile_node - 观众画像节点

### 为什么爬取
提取短剧观众画像数据：
- 性别比例（女70%/男30%）
- 年龄分布（18-24、25-34、35-44、45+）
- 地域分布（TOP10省份）

### System Prompt (SP)
```
你是一个人口统计学分析师。根据输入的搜索资料，提炼短剧观众的最新画像数据。
如果资料缺失，请使用2026年短剧行业默认经验数据填充，不得报错。
必须输出合法的 JSON 对象。
```

#### User Prompt (UP)
```
【搜索资料】：
{{search_context}}

请提取并输出 JSON，必须包含：
{
  "gender": {"female": 70, "male": 30}, 
  "age": {"18-24": 25, "25-34": 40, "35-44": 25, "45+": 10}, 
  "regions": [{"name": "广东", "value": 15}, {"name": "浙江", "value": 10}]
}
```

### 配置文件
| 参数 | 值 |
|------|-----|
| model | deepseek-chat |
| temperature | 0.1 |
| max_completion_tokens | 800 |

---

## 节点调用顺序

```
search_node (爬取基础数据)
    ↓
process_node (解析数据)
    ↓
enrich_node (补全厂牌/爽点)
    ↓
┌─────────────────────────────────────┐
│ industry_node (行业大盘)            │
│ audience_profile_node (观众画像)    │
│ genre_distribution_node (题材分布)  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ actor_ranking_node (演员榜单)       │
│ insights_node (行业大事件)          │
│ news_node (行业快讯)                │
└─────────────────────────────────────┘
    ↓
history_data_node (历史数据汇总)
    ↓
push_node (保存数据)
```

---

## 重要规则总结

| 规则 | 说明 |
|------|------|
| 禁止Mock | 所有数据必须来自DeepSeek真实搜索 |
| 具体数据 | 禁止泛泛分析，必须有剧目名、播放量等具体数值 |
| 原文链接 | 行业快讯必须有source_url原文链接，不是门户网站首页 |
| 100字限制 | 快讯content不超过100字 |
| 5条快讯 | 行业快讯必须输出5条 |
| Pydantic访问 | 使用`.field_name`属性访问，禁止`.get()` |

---

## 配置文件位置

| 节点 | 配置文件 |
|------|----------|
| news_node | `config/news_llm_cfg.json` |
| enrich_node | `config/enrich_llm_cfg.json` |
| actor_ranking_node | `config/actor_ranking_llm_cfg.json` |
| industry_node | `config/industry_llm_cfg.json` |
| insights_node | `config/insights_llm_cfg.json` |
| audience_profile_node | `config/audience_profile_llm_cfg.json` |