# 热门内容频道开发记录

> 用于在新窗口/新会话中快速恢复上下文。记录日期：2026-06-28。

## 1. 项目背景

在主看板「短剧行业新闻」之外，新增一个并列频道 **「热门内容」**。该频道聚焦近期热门短剧/小说，为创作者提供题材灵感。

## 2. 已确定事项

### 2.1 频道定位

- **更新频率**：周更（每周一执行）
- **数据来源**：
  - 红果短剧：首页热门推荐 Top 10
  - 晋江小说：手机站霸王票日榜 Top 10
  - 番茄小说：首页 `weekList` 本周推荐 8 本 + `editorList` 编辑推荐补 2 本 = 10 本
- **每部作品字段**：标题、作者、平台、封面、原文链接、200 字自行理解摘要、分类标签、热度

### 2.2 数据源验证结果

| 平台 | 数据源 | 状态 | 说明 |
|---|---|---|---|
| 红果 | `HongguoCrawler.fetch_homepage_list()` | ✅ 可行 | 已有爬虫，取 Top 10 |
| 晋江 | `https://m.jjwxc.net/ranks/kingticket` | ✅ 可行 | 手机站霸王票日榜，数据近期且每日变化 |
| 番茄 | `fanqienovel.com` 首页 `weekList` + `editorList` | ✅ 可行 | `weekList` 8 本，`editorList` 补 2 本 |

### 2.3 JSON Schema

文件位置：`assets/data/hot_content/latest.json`

```json
{
  "data_date": "2026-06-30",
  "week_label": "2026.06.30 - 07.06",
  "update_time": "2026-06-30 09:00:00",
  "total_items": 30,
  "sections": [
    {
      "platform": "红果短剧",
      "platform_key": "hongguo",
      "source_url": "https://novelquickapp.com/",
      "update_frequency": "周更",
      "item_count": 10,
      "items": [
        {
          "rank": 1,
          "title": "...",
          "author": "",
          "cover_url": "...",
          "original_url": "...",
          "summary": "200字自行理解摘要",
          "tags": ["...", "..."],
          "heat": 12000,
          "heat_text": "热度 12000",
          "extra": {
            "episodes": "全80集",
            "genre": "都市"
          }
        }
      ]
    },
    {
      "platform": "晋江小说",
      "platform_key": "jjwxc",
      "source_url": "https://m.jjwxc.net/ranks/kingticket",
      "update_frequency": "周更（基于日榜快照）",
      "item_count": 10,
      "items": [...]
    },
    {
      "platform": "番茄小说",
      "platform_key": "fanqie",
      "source_url": "https://fanqienovel.com/",
      "update_frequency": "周更",
      "item_count": 10,
      "items": [...]
    }
  ]
}
```

### 2.4 文件路径

```
assets/data/hot_content/
├── latest.json              # 本周最新内容
├── index.json               # 历史周索引
└── weekly/
    ├── 2026-06-30.json
    ├── 2026-06-23.json
    └── ...
```

## 3. 当前进度

- [x] 前端 HTML 已新增「热门内容」Tab 框架
- [x] 三个平台数据源可行性验证完成
- [x] 阶段二：写爬虫并输出原始 JSON（已完成）
- [x] 阶段三：内容分析（200 字摘要 + 标签）（已完成，本地规则降级可用，GitHub Actions 有 DEEPSEEK_API_KEY 时会走 LLM）
- [ ] 阶段四：工作流集成（每周一执行）
- [x] 阶段五：前端渲染热门内容（已完成）
- [ ] 阶段六：测试上线

## 4. 阶段二任务清单

### 4.1 新建/修改文件

| 文件 | 作用 |
|---|---|
| `src/tools/jjwxc_mobile_crawler.py` | 晋江手机站霸王票日榜爬虫 |
| `src/tools/fanqie_crawler.py` | 番茄首页 weekList + editorList 爬虫 |
| `src/tools/hongguo_crawler.py` | 复用现有红果爬虫，补充 original_url |
| `scripts/fetch_hot_content_raw.py` | 统一抓取入口，输出原始 JSON |

### 4.2 临时输出

- 文件：`tmp/hot_content_raw_YYYYMMDD.json`
- 内容：按 Schema 对齐，但 `summary` 暂放官方简介/原始描述

### 4.3 验证结果（2026-06-28）

- [x] 晋江爬虫稳定输出 10 条
- [x] 番茄爬虫稳定输出 10 条（8 weekList + 2 editorList）
- [x] 红果爬虫稳定输出 10 条
- [x] 统一脚本输出完整 raw JSON
- [x] 连续跑 2 次数据稳定（结构稳定；晋江日榜自然会有少量位次变化，符合预期）

**测试命令：**
```bash
cd "/Users/Zhuanz/Documents/2606 Shortvideo/Shortvideo_news"
source .venv/bin/activate
PYTHONPATH=src python3 scripts/fetch_hot_content_raw.py
```

**输出文件：**
- `tmp/hot_content_raw_YYYY-MM-DD.json`
- 示例：`tmp/hot_content_raw_2026-06-22.json`

## 5. 新增文件说明

| 文件 | 作用 |
|---|---|
| `src/tools/hot_content_fetcher.py` | 统一抓取三个平台原始数据 |
| `src/tools/hot_content_analyzer.py` | DeepSeek LLM 分析 + 本地规则降级 |
| `scripts/generate_hot_content.py` | 完整流程：抓取 → 分析 → 输出最终 JSON |
| `assets/index.html` | 已新增「热门内容」频道前端渲染 |

## 6. 前端设计

- 左侧：历史周次导航栏（桌面端固定，移动端变为顶部下拉）
- 右侧顶部：平台筛选 Tab（全部 / 红果 / 晋江 / 番茄）
- 右侧主体：单列卡片流，一行一张卡片
- 每张卡片：封面 + 平台徽章 + 排名 + 标题 + 作者 + 热度 + 200 字摘要 + 标签
- 平台配色：红果（粉红/玫瑰）、晋江（青绿）、番茄（金黄/橙）

## 7. 运行命令

```bash
cd "/Users/Zhuanz/Documents/2606 Shortvideo/Shortvideo_news"
source .venv/bin/activate
PYTHONPATH=src python3 scripts/generate_hot_content.py
```

**输出文件：**
- `assets/data/hot_content/latest.json`
- `assets/data/hot_content/weekly/YYYY-MM-DD.json`
- `assets/data/hot_content/index.json`

## 8. 注意事项

- 晋江手机站使用 **gb18030** 编码，需要 gzip 解压
- 番茄首页数据在 `window.__INITIAL_STATE__.home.weekList` / `editorList`
- 红果首页数据在 `window._ROUTER_DATA`
- 本地无 `DEEPSEEK_API_KEY` 时，自动降级为本地规则生成摘要
- GitHub Actions 中注入 `DEEPSEEK_API_KEY` 后，会调用 DeepSeek API 生成高质量摘要
- `tmp/` 已加入 `.gitignore`，不会被提交

## 9. 下一步

- 阶段四：GitHub Actions 每周一自动执行 `scripts/generate_hot_content.py`
- 阶段六：在真实环境中测试 2-3 周，观察数据质量和前端展示效果
