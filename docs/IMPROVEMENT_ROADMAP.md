# 短剧行业数据看板 - 改进路线图

> 当前基线：v1.5.0，Kimi (Moonshot) API + GitHub Actions + 静态 Dashboard。  
> 本文记录代码审视后的风险、优先级和建议改进方向。

---

## 当前状态判断

### 已经稳定的部分

- GitHub Actions 可以定时/手动执行，并将 `assets/data/` 与 `assets/history_data.json` 自动提交。
- 前端看板已改为读取 `assets/data/latest.json`，并支持历史日期下拉。
- 前端已展示 `error_message` 数据质量提示，便于发现节点级错误。
- Kimi 联网搜索已通过官方 `$web_search` 工具调用，不再只依赖 prompt 触发搜索。
- JSON 解析器已统一收敛到 `MoonshotClient`，解析失败会打印 Kimi 原始返回文本。
- 节点失败会写入 `error_message`，方便从 `latest.json` 和 Actions 日志定位问题。

### 当前主要风险

| 优先级 | 风险 | 表现 | 建议 |
|---|---|---|---|
| P0 | 数据真实性不稳定 | Kimi 可能返回非短剧演员或传统影视演员 | 增加来源校验与置信度字段 |
| P0 | 榜单源不够稳定 | 搜索结果可能混入“示例剧名”或非今日榜单 | 建立榜单数据源白名单与质量门禁 |
| P1 | 题材分布偏粗 | 当前 `genre` 常为空，题材聚合为“其他” | 在 process/enrich 阶段强制补齐标准题材 |
| P1 | 宏观数据格式不统一 | `user_scale` 可能是数字、字符串或对象 | 输出前统一格式化为 `{value, unit, source}` |
| P1 | 数据质量提示还比较基础 | 页面已展示 `error_message`，但缺少结构化分级 | 后续改成“质量分数+警告列表+节点状态” |
| P2 | 文档仍有历史架构痕迹 | 部分长文档仍描述 Coze/旧分层 | 后续拆分“当前架构”和“历史记录” |

---

## 推荐改进方向

### 1. 数据质量门禁（最高优先级）

目标：宁可少展示，也不要展示明显错误的数据。

建议新增一个 `quality_gate_node`，在 `push_node` 前执行：

- 检查 `rankings` 数量是否达到最低阈值（如 >= 5）
- 检查 `rank/title/views/platform` 是否完整
- 检查 `views_num` 是否为合理正数
- 检查演员是否命中“传统影视明星高风险名单”
- 检查 `error_message` 是否包含 API 鉴权/解析失败

建议输出：

```json
{
  "quality_score": 86,
  "quality_warnings": [
    "2部剧演员缺少可信来源",
    "3部剧genre为空"
  ],
  "data_tier": "verified/search/inferred"
}
```

### 2. 演员与厂牌可信度校验

当前仅依赖 Kimi 搜索和抽取，仍可能出现传统影视演员混入。

建议：

- 为每部剧新增：
  - `source_url`
  - `source_title`
  - `actor_confidence`
  - `production_confidence`
- 若演员没有明确网页来源，统一填 `"未知"`，不要让模型“猜”。
- 维护一个 `config/actor_blocklist.json`，先覆盖高频误判：
  - 刘亦菲、杨幂、胡歌、林更新、李一桐等传统长剧演员。

### 3. 榜单数据源白名单

建议优先使用以下类型来源：

- DataEye 短剧热力榜
- 新腕儿短剧榜单
- 红果/抖音/快手公开榜单
- 云合/QuestMobile 行业报告

不建议直接采用：

- 小说 IP 名单
- 影视剧通稿
- 无来源的泛文章
- 社交平台二次搬运内容

### 4. 题材标准化

当前很多 `genre` 为空，导致题材分布显示“其他”。

建议定义标准枚举：

```text
都市甜宠、都市逆袭、重生复仇、古装权谋、年代情感、战神赘婿、玄幻脑洞、悬疑推理、AI短剧、其他
```

在 `enrich_node` 中强制输出标准题材，并把 `core_trope` 控制在 2-3 个标签。

### 5. Dashboard 数据质量可视化

基础版已完成：当前前端会显示 `latest.json.error_message`。后续建议升级为结构化小模块：

- 数据质量分数
- 本次数据源数量
- 节点错误信息（折叠展示）
- 更新时间

这样当 `latest.json` 有错误时，页面不会只显示“空数据”，而是能告诉用户问题出在哪个节点。

---

## 建议实施顺序

1. 新增 `quality_gate_node`，阻止明显低质量数据覆盖正常页面。
2. 增加演员/厂牌来源字段与置信度。
3. 修正 process/enrich prompt，要求 `genre` 必填且来自标准枚举。
4. 前端增加数据质量提示模块。
5. 将旧文档拆分为：
   - `CURRENT_ARCHITECTURE.md`
   - `LEGACY_COZE_ARCHITECTURE.md`

---

## 当前不建议做的事

- 不建议把更多数据写死进 `index.html`。
- 不建议用大量硬编码 mock 数据修补榜单。
- 不建议仅靠 prompt 约束“不要乱编”，应增加代码层校验。
- 不建议继续扩大节点数量，优先把现有节点的数据质量闭环做好。
