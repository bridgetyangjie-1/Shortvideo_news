# Dashboard UI 设计规范

> Gemini 提供的短剧行业商业决策看板设计规范 - DeepSeek Powered

## 一、整体风格

### 1.1 品牌标识
- **标题**: "短剧行业数据看板 - Bridget Yang"
- **AI Badge**: 🤖 DeepSeek Powered + Tier 1+2+3标识
- **渐变效果**: linear-gradient(135deg, #e0e7ff 0%, #818cf8 100%)

### 1.2 背景设计
```css
background: #0b0d14;
/* 深度紫蓝背景光晕 */
background::before {
  background: radial-gradient(circle at 50% 0%, rgba(99, 102, 241, 0.12), transparent 55%);
}
```

### 1.3 玻璃态卡片（Glass Card）
```css
.glass-card {
  background: rgba(22, 25, 37, 0.65);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.2);
}
.glass-card:hover {
  border-color: rgba(99, 102, 241, 0.4);
  box-shadow: 0 8px 32px rgba(99, 102, 241, 0.15);
  transform: translateY(-2px);
}
```

---

## 二、配色方案

### 2.1 主色调
| 名称 | 色值 | 用途 |
|------|------|------|
| 主背景 | #0b0d14 | 页面背景 |
| 卡片背景 | rgba(22, 25, 37, 0.65) | 玻璃态卡片 |
| 强调色 | #818cf8 / #a78bfa | 紫色渐变、AI元素 |
| 成功色 | #34d399 | 增长标记、流量洼地 |
| 危险色 | #fb7185 | 下降标记、红海预警 |
| 金色 | #facc15 | 金额、商业指标 |

### 2.2 文字色
| 名称 | 色值 | 用途 |
|------|------|------|
| 主文字 | #f8fafc | 标题、重要数值 |
| 次文字 | #e2e8f0 | 正文内容 |
| 辅助文字 | #94a3b8 | 标签、说明 |
| 弱文字 | #64748b | 描述、次要信息 |

---

## 三、布局结构

### 3.1 页面分区
```
┌──────────────────────────────────────────────────────┐
│ Header: 标题 + AI Badge + 时间选择器                   │
├──────────────────────────────────────────────────────┤
│ KPI双列网格: 左侧商业指标 | 右侧投流风向标              │
├──────────────────────────────────────────────────────┤
│ 榜单TOP10表格: 排名徽章 + 剧名 + 主演 + 播放量 + 题材   │
├──────────────────────────────────────────────────────┤
│ 演员榜: 女频TOP5(粉色) | 男频TOP5(蓝色)                │
├──────────────────────────────────────────────────────┤
│ 行业快讯(daily_news): Emoji分类 + 一句话快讯          │
├──────────────────────────────────────────────────────┤
│ 异动点评(insights): 简洁商业建议(最多2条)             │
├──────────────────────────────────────────────────────┤
│ 趋势图表: Chart.js播放量曲线 + AI占比曲线              │
└──────────────────────────────────────────────────────┘
```

### 3.2 KPI卡片设计
```html
<div class="kpi-card commercial">
  <div class="kpi-icon">💰</div>
  <div class="kpi-value money">1000亿+</div>
  <div class="kpi-label">市场规模</div>
  <div class="kpi-trend up">↑ 25%</div>
</div>
```

---

## 四、组件样式

### 4.1 排名徽章（Rank Badge）
| 排名 | CSS类名 | 效果 |
|------|---------|------|
| 1 | .gold | 金色渐变 + shadow发光 |
| 2 | .silver | 银灰渐变 |
| 3 | .bronze | 铜色渐变 |
| 4-10 | .normal | 半透明背景 |

```css
.rank-badge.gold {
  background: linear-gradient(135deg, #fbbf24, #d97706);
  box-shadow: 0 4px 10px rgba(217, 119, 6, 0.3);
}
```

### 4.2 AI标签（AI Tag）
```css
.ai-tag {
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 6px;
  color: #818cf8;
}
```

### 4.3 快讯卡片样式
```html
<!-- 行业快讯 daily_news -->
<div class="news-item">
  <span class="news-emoji">⚠️</span>
  <span class="news-type">预警</span>
  <span class="news-content">广电总局新规要求短剧备案...</span>
</div>
```

Emoji分类：
- ⚠️ 预警：政策收紧、投流规则改变
- 🚀 商业：爆款剧集、大厂动作、融资消息
- 📊 数据：常规数据、榜单更新

---

## 五、数据分层标识

### 5.1 Tier质量保证可视化
```
┌────────────────────────────────────────────┐
│ Tier 1: Coze爬取 → 100%真实（榜单、播放量） │
│ Tier 2: DeepSeek搜补 → 80%可信（主演、题材） │
│ Tier 3: DeepSeek推理 → 参考价值（洞察、风向）│
└────────────────────────────────────────────┘
```

### 5.2 字段来源标记
- 🟢 Tier 1 字段：不加标记
- 🟡 Tier 2 字段：标记"待DeepSeek补全"
- 🔴 Tier 3 字段：标记"AI推理生成"

---

## 六、新增模块规范

### 6.1 行业快讯模块（daily_news）
位置：榜单表格上方，KPI卡片下方

```html
<div class="glass-card">
  <h3 class="section-title">📰 今日行业快讯</h3>
  <div class="news-grid">
    <!-- 最多5条快讯 -->
    <div class="news-item">
      <span class="news-emoji">🚀</span>
      <span class="news-content">红果短剧完成新一轮融资...</span>
    </div>
  </div>
</div>
```

### 6.2 异动点评模块（insights）
位置：快讯下方

```html
<div class="glass-card">
  <h3 class="section-title">💡 异动点评</h3>
  <div class="insights-list">
    <!-- 最多2条点评 -->
    <div class="insight-item">
      <span class="insight-icon">📈</span>
      <div class="insight-content">甜宠题材霸榜，建议加大投流...</div>
    </div>
  </div>
  <!-- 大盘平稳时显示 -->
  <div class="insight-stable">大盘平稳，维持常规投流策略即可。</div>
</div>
```

---

## 七、响应式设计

### 7.1 断点设置
| 设备 | 断点 | 调整 |
|------|------|------|
| 手机 | <768px | 单列布局、缩小字体 |
| 平板 | 768-1024px | 双列布局 |
| 桌面 | >1024px | 三列布局 |

### 7.2 表格适配
```css
@media (max-width: 768px) {
  .rankings-table { font-size: 12px; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
```

---

## 八、注意事项

### 8.1 不再变动的设计元素
- ✅ 整体背景色 (#0b0d14)
- ✅ 玻璃态卡片样式
- ✅ AI Badge位置和样式
- ✅ 排名徽章渐变效果
- ✅ 配色方案

### 8.2 可扩展的元素
- 🔧 新增daily_news快讯模块
- 🔧 调整insights为异动点评（最多2条）
- 🔧 新增投流风向标模块（market_signals）

---

## 九、文件说明

| 文件 | 用途 |
|------|------|
| `docs/UI_DESIGN.md` | 本文档，UI设计规范 |
| `assets/index.html` | Dashboard HTML实现 |
| `assets/data/latest.json` | 数据源文件 |

**注意**: UI设计已固化为本MD文档，HTML实现应严格遵循此规范。