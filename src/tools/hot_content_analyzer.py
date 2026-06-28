"""
热门内容分析器
使用 DeepSeek API 把原始简介改写成 200 字自行理解摘要，并提炼标签。
无 API key 或 API 失败时，降级为本地规则生成。
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from tools.deepseek_api import DeepSeekClient

logger = logging.getLogger(__name__)


# 常见题材/情绪关键词，用于本地规则推断标签
TAG_KEYWORDS = {
    "重生": "重生",
    "穿越": "穿越",
    "穿书": "穿书",
    "年代": "年代文",
    "八零": "年代文",
    "七零": "年代文",
    "九零": "年代文",
    "末世": "末世",
    "修仙": "修仙",
    "仙侠": "仙侠",
    "玄幻": "玄幻",
    "悬疑": "悬疑",
    "灵异": "悬疑灵异",
    "甜宠": "甜宠",
    "甜文": "甜宠",
    "虐": "虐恋",
    "逆袭": "逆袭",
    "打脸": "打脸爽文",
    "爽文": "爽文",
    "大女主": "大女主",
    "总裁": "总裁",
    "豪门": "豪门",
    "宫斗": "宫斗宅斗",
    "宅斗": "宫斗宅斗",
    "种田": "种田",
    "萌宝": "萌宝",
    "系统": "系统",
    "金手指": "金手指",
    "先婚后爱": "先婚后爱",
    "闪婚": "闪婚",
    "带球跑": "带球跑",
    "真假千金": "真假千金",
    "替身": "替身",
    "马甲": "马甲",
    "复仇": "复仇",
    "军婚": "军婚",
    "年代文": "年代文",
    "民国": "民国",
    "古穿今": "古穿今",
    "古言": "古言",
    "现言": "现言",
    "都市": "都市",
    "校园": "校园",
    "职场": "职场婚恋",
    "婚恋": "职场婚恋",
    "破镜重圆": "破镜重圆",
    "追妻": "追妻火葬场",
    "追夫": "追夫火葬场",
    "火葬场": "追妻火葬场",
    "反派": "反派",
    "无限流": "无限流",
    "快穿": "快穿",
    "星际": "星际",
    "abo": "ABO",
    "娱乐圈": "娱乐圈",
    "美食": "美食",
    "经营": "经营",
    "神豪": "神豪流",
    "囤货": "囤货",
    "基建": "基建",
    "科举": "科举",
    "权谋": "权谋",
    "武侠": "武侠",
    "科幻": "科幻",
    "奇幻": "奇幻",
}


def _extract_tags_from_text(text: str, existing_tags: List[str]) -> List[str]:
    """从文本中提取标签，并和已有标签合并去重"""
    text = text.lower()
    inferred = []
    for keyword, tag in TAG_KEYWORDS.items():
        if keyword in text and tag not in inferred:
            inferred.append(tag)

    # 合并已有标签
    merged = []
    for t in existing_tags:
        t_clean = t.strip()
        if t_clean and t_clean not in merged:
            merged.append(t_clean)

    for t in inferred:
        if t not in merged:
            merged.append(t)

    return merged[:5]


def _local_summary(item: Dict[str, Any]) -> str:
    """本地规则生成摘要"""
    title = item.get("title", "")
    platform = item.get("platform_key", "")
    raw_summary = item.get("summary", "")
    tags = item.get("tags", []) or []
    category = item.get("extra", {}).get("category", "")
    one_line = item.get("extra", {}).get("one_line", "")

    if platform == "hongguo":
        # 红果没有原始简介，基于标题+标签生成更丰富的摘要
        tag_str = "、".join(tags[:4]) if tags else "热门"
        episodes = item.get("extra", {}).get("episodes", "")
        ep_text = f"，{episodes}" if episodes else ""
        core_tag = tags[0] if tags else "热门题材"

        # 从标题和标签中推断核心看点
        title_lower = title.lower()
        text_for_hooks = f"{title_lower} {tag_str}"
        hook_points = []
        hook_rules = [
            ("重生", "重生逆袭"),
            ("公主", "身份尊荣"),
            ("王妃", "身份尊荣"),
            ("嫡女", "身份尊荣"),
            ("总裁", "权势爱情"),
            ("老板", "权势爱情"),
            ("真假千金", "身份错位"),
            ("真千金", "身份错位"),
            ("马甲", "隐藏身份"),
            ("打脸", "打脸爽感"),
            ("虐渣", "打脸爽感"),
            ("替嫁", "契约情感"),
            ("先婚后爱", "契约情感"),
            ("闪婚", "契约情感"),
            ("逃婚", "契约情感"),
            ("追妻", "情感博弈"),
            ("追夫", "情感博弈"),
            ("萌宝", "亲子羁绊"),
            ("系统", "系统金手指"),
            ("金手指", "系统金手指"),
            ("穿越", "穿越逆袭"),
            ("穿书", "穿书逆袭"),
            ("年代", "年代奋斗"),
            ("八零", "年代奋斗"),
            ("七零", "年代奋斗"),
            ("九零", "年代奋斗"),
            ("战神", "战神归来"),
            ("神豪", "神豪逆袭"),
            ("医妃", "医术逆袭"),
            ("神医", "医术逆袭"),
        ]
        for keyword, hook in hook_rules:
            if keyword in text_for_hooks and hook not in hook_points:
                hook_points.append(hook)
        if not hook_points:
            hook_points = ["强冲突", "高反转"]
        hook_str = "、".join(hook_points[:3])

        return (
            f"《{title}》是一部{tag_str}题材短剧{ep_text}。"
            f"剧情以{hook_str}为核心看点，围绕主角在极端情境下的身份博弈与命运反转展开，"
            f"通过高密度反转与强情绪钩子推进叙事，精准切中观众对爽感与情绪释放的需求，"
            f"是{core_tag}赛道值得参考的内容样本。"
        )

    # 晋江/番茄：有原始简介，清洗后截取/压缩
    source = "小说" if platform in ("jjwxc", "fanqie") else "作品"
    text = raw_summary or one_line or category
    text = re.sub(r"\s+", " ", text).strip()

    # 去掉常见的作者自语/广告
    for marker in ["下本开", "预收", "下一本", "求收藏", "________________"]:
        idx = text.find(marker)
        if idx != -1 and idx > 20:
            text = text[:idx].strip()

    # 截取前 200 字
    if len(text) > 200:
        text = text[:197] + "..."

    if not text:
        text = "暂无简介"

    tag_str = "、".join(tags[:3]) if tags else "热门"
    return (
        f"《{title}》是一部{tag_str}{source}。"
        f"{text}"
    )


def _local_analyze(item: Dict[str, Any]) -> Dict[str, Any]:
    """本地规则分析单本书"""
    summary = _local_summary(item)
    tags = _extract_tags_from_text(
        f"{item.get('title', '')} {item.get('summary', '')} {item.get('extra', {}).get('category', '')}",
        item.get("tags", []) or [],
    )

    return {
        "summary": summary,
        "tags": tags if tags else ["热门"],
        "appeal": _generate_appeal(item, tags),
    }


def _generate_appeal(item: Dict[str, Any], tags: List[str]) -> str:
    """生成本地一句话卖点"""
    # 优先直接用已有标签
    for tag in tags:
        normalized = tag.strip()
        if normalized in TAG_KEYWORDS.values():
            return f"{normalized}看点十足"

    # 其次从标题和标签中匹配关键词
    title = item.get("title", "")
    text = f"{title} {' '.join(tags)}"
    for keyword, tag in TAG_KEYWORDS.items():
        if keyword in text:
            return f"{tag}看点十足"
    return "热门好文"


def _build_deepseek_prompt(items: List[Dict[str, Any]]) -> str:
    """为 DeepSeek 构建批量分析 prompt"""
    lines = [
        "你是一位网络文学和短剧内容分析专家。请把以下作品的官方简介改写成创作者视角的 200 字内容解读，并提炼分类标签。",
        "",
        "要求：",
        "1. summary：200字左右，不要复制官方文案。说明核心冲突、爽点、人设、情绪价值。",
        "2. tags：3-5个分类标签，如\"重生逆袭\"\"甜宠\"\"年代文\"\"悬疑\"\"大女主\"等。",
        "3. appeal：一句话卖点，15字以内。",
        "4. 输出严格 JSON 数组格式，每个元素对应一本书，按输入顺序。",
        "",
        "输出格式示例：",
        '[{"title":"书名","summary":"...","tags":["..."],"appeal":"..."}]',
        "",
        "待分析作品：",
    ]

    for i, item in enumerate(items, start=1):
        lines.append(f"\n【作品{i}】")
        lines.append(f"平台：{item.get('platform', '')}")
        lines.append(f"标题：《{item.get('title', '')}》")
        if item.get("author"):
            lines.append(f"作者：{item.get('author', '')}")
        if item.get("extra", {}).get("category"):
            lines.append(f"分类：{item.get('extra', {}).get('category', '')}")
        raw_summary = item.get("summary", "")
        if raw_summary:
            # 控制原始简介长度，避免 token 爆炸
            raw_summary = raw_summary[:800]
            lines.append(f"原始简介：{raw_summary}")
        existing_tags = item.get("tags", [])
        if existing_tags:
            lines.append(f"已有标签：{', '.join(existing_tags[:5])}")

    return "\n".join(lines)


def _parse_deepseek_response(content: str, expected_titles: List[str]) -> List[Dict[str, Any]]:
    """解析 DeepSeek 返回的 JSON"""
    # 先尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试找第一个 [ 和最后一个 ]
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.error(f"无法解析 DeepSeek 响应: {content[:200]}")
    return []


class HotContentAnalyzer:
    """热门内容分析器"""

    def __init__(self, batch_size: int = 5):
        self.batch_size = batch_size
        self.client = DeepSeekClient()
        self.use_llm = self.client.api_key and self.client.api_key != "missing-deepseek-api-key"
        if not self.use_llm:
            logger.warning("DEEPSEEK_API_KEY 未设置，将使用本地规则生成摘要")

    def analyze_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量分析作品，返回带 summary/tags/appeal 的结果。
        如果 DeepSeek 不可用，自动降级为本地规则。
        """
        if not self.use_llm:
            logger.info("使用本地规则分析")
            return [self._analyze_single(item, use_llm=False) for item in items]

        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            try:
                batch_results = self._analyze_with_deepseek(batch)
                results.extend(batch_results)
            except Exception as e:
                logger.error(f"DeepSeek 批量分析失败，降级为本地规则: {e}")
                for item in batch:
                    results.append(self._analyze_single(item, use_llm=False))
        return results

    def _analyze_with_deepseek(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """调用 DeepSeek API 分析一批作品"""
        prompt = _build_deepseek_prompt(batch)
        messages = [
            {
                "role": "system",
                "content": "你是一位擅长内容解读的网络文学和短剧分析专家，输出严格 JSON。",
            },
            {"role": "user", "content": prompt},
        ]

        response = self.client.chat(messages, temperature=0.5, max_tokens=4000)
        parsed = _parse_deepseek_response(response, [item["title"] for item in batch])

        if len(parsed) != len(batch):
            logger.warning(f"DeepSeek 返回数量不匹配: 期望 {len(batch)}, 实际 {len(parsed)}")

        results = []
        for item, analysis in zip(batch, parsed):
            results.append(self._merge_analysis(item, analysis))

        return results

    def _analyze_single(self, item: Dict[str, Any], use_llm: bool = False) -> Dict[str, Any]:
        """分析单本书"""
        if use_llm:
            try:
                return self._analyze_with_deepseek([item])[0]
            except Exception as e:
                logger.error(f"单本 DeepSeek 分析失败: {e}")

        local = _local_analyze(item)
        return self._merge_analysis(item, local)

    def _merge_analysis(
        self, item: Dict[str, Any], analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """把分析结果合并回原数据"""
        result = dict(item)
        result["summary"] = analysis.get("summary", item.get("summary", ""))
        result["tags"] = analysis.get("tags", item.get("tags", [])) or []
        result["appeal"] = analysis.get("appeal", "")

        # summary 长度控制
        summary = result["summary"]
        if len(summary) > 250:
            summary = summary[:247] + "..."
        result["summary"] = summary

        # tags 数量控制
        result["tags"] = result["tags"][:5]

        return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = HotContentAnalyzer()
    test_items = [
        {
            "title": "女主她缺大德[八零]",
            "platform_key": "jjwxc",
            "author": "四单铺",
            "summary": "穿进年代文的萧弘瑶，满腔热血，只想搞钱，千方百计嫁给反派大佬...",
            "tags": ["打脸", "穿书", "爽文", "年代文"],
            "extra": {"category": "原创-言情-近代现代-爱情-女主视角"},
        }
    ]
    results = analyzer.analyze_items(test_items)
    print(json.dumps(results[0], ensure_ascii=False, indent=2))
