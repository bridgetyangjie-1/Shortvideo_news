# 短剧行业数据看板 - AGENTS规范文档

---

## 📌 版本信息

| 版本 | Tag | 日期 | 说明 |
|------|-----|------|------|
| **标准版本** | `v1.0.0` | 2026-06-09 | 首个稳定版本，未来修改基于此版本 |
| v1.1.0 | - | 2026-06-09 | 标题改为"短剧行业数据看板"，添加作者Bridget Yang |
| v1.1.1 | - | 2026-06-10 | AI异动点评改为"行业大事件"，生成具体事件+数据 |
| v1.2.0 | - | 2026-06-10 | 题材分布新增标签热度，修复数据渲染问题 |
| **当前版本** | `v1.5.0` | 2026-06-10 | **切换到Kimi (Moonshot) API替代DeepSeek/DuckDuckGo** |

**回滚到标准版本**：
```bash
git checkout v1.0.0
```

---

## ⚠️ 重要注意事项

### Kimi (Moonshot) API架构（v1.5.0）
**国内联网搜索能力强，可穿透微信、知乎等数据孤岛**

核心改动：
- **moonshot_api.py**: 新建MoonshotClient工具类，使用OpenAI SDK标准格式
- **所有节点**: DeepSeekClient → MoonshotClient
- **删除**: deepseek_api.py（已废弃）

优势：
- ✅ Kimi自带联网搜索能力（无需额外搜索引擎）
- ✅ 国内数据源覆盖强（微信公众号、小红书、知乎等）
- ✅ 32k上下文窗口，支持长文本处理
- ✅ base_url: https://api.moonshot.cn/v1，模型: moonshot-v1-32k

⚠️ GitHub Actions环境变量：
- `MOONSHOT_API_KEY` - 已配置

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
**禁止对Pydantic对象使用`.get()`方法！**
```python
# ❌ 错误 - Pydantic对象没有.get()方法
rankings.get('title')

# ✅ 正确 - 使用属性访问
rankings.title
```

### Gemini架构重构（v1.3.0）
**根除"物理断层"问题 - Prompt命令搜索但Python只调用chat**

核心改动：
- **enrich_node**: 先在Python层为每部剧调用`client.search()`获取真实资料，再喂给LLM做提取
- **insights_node**: 使用`client.search()`而非`client.chat()`，真正触发联网搜索

验证结果：
- ✅ 演员不再显示传统影视明星（刘亦菲、胡歌等）
- ✅ 演员为真实短剧演员（徐艺真、孙樾、王格格等）
- ✅ 洞察有爆款归因+买量建议

---

## 项目概述

- **名称**: 短剧行业数据看板
- **作者**: Bridget Yang
- **功能**: 使用DeepSeek API自动抓取短剧行业数据，生成多维度分析报告
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
- **内容**: 100字内总结（DeepSeek提炼）
- **链接**: 具体原文链接（非门户网站首页）
- **类型**: data/warn/biz（数据/预警/商业）

### 行业大事件规则（v1.1.1要求）
- **内容**: 具体事件+真实数据（如"播放量暴涨45%"）
- **来源**: DeepSeek联网搜索实时事件
- **禁止**: 泛泛分析（如"女频剧持续领跑"）

---

## 节点清单

| 节点名 | 文件位置 | 类型 | 功能描述 | 配置文件 |
|-------|---------|------|---------|---------|
| search_node | `nodes/search_node.py` | task | DeepSeek联网搜索榜单+标签数据 | - |
| news_node | `nodes/news_node.py` | agent | DeepSeek搜索5条快讯+100字总结+原文链接 | `config/news_llm_cfg.json` |
| process_node | `nodes/process_node.py` | agent | DeepSeek结构化处理榜单 | `config/process_llm_cfg.json` |
| enrich_node | `nodes/enrich_node.py` | agent | **先搜后问架构** - Python层调用search获取真实资料，再喂给LLM提取演员/标签 | `config/enrich_llm_cfg.json` |
| actor_ranking_node | `nodes/actor_ranking_node.py` | agent | DeepSeek生成演员人气榜 | `config/actor_ranking_llm_cfg.json` |
| industry_node | `nodes/industry_node.py` | agent | DeepSeek联网获取行业宏观数据 | `config/industry_llm_cfg.json` |
| audience_profile_node | `nodes/audience_profile_node.py` | agent | DeepSeek搜索观众画像 | `config/audience_profile_llm_cfg.json` |
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
- **名称**: `DEEPSEEK_API_KEY`
- **值**: 你的DeepSeek API密钥

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
│   │   └── deepseek_api.py # DeepSeek API工具
│   ├── utils/
│   │   └── runtime.py      # Context替代类
│   └── run_github.py       # GitHub Actions入口
├── AGENTS.md               # 本文件
└── .gitignore              # 忽略截屏图片等
```