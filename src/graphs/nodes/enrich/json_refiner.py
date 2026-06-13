"""
JSON 推理精修器：调用 DeepSeek 补全榜单字段并解析 JSON。
"""
import json
import logging
import re
from typing import Any, Dict, List

from tools.deepseek_api import DeepSeekClient

logger = logging.getLogger(__name__)


class JsonRefiner:
    """使用 DeepSeek 对榜单数据进行 JSON 推理与精修。"""

    def __init__(self, client: DeepSeekClient):
        self.client = client

    def refine(
        self,
        basic_rankings: List[Any],
        search_context: str,
        data_date: str,
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        基于基础榜单和搜索上下文，调用 DeepSeek 生成完整榜单 JSON。

        Returns:
            榜单字典列表（可能为空）
        """
        rankings_json_list = self._normalize_rankings(basic_rankings)
        if not rankings_json_list:
            return []

        user_prompt = self._build_prompt(rankings_json_list, search_context, data_date)

        response = self.client.chat(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                    or "你是数据提取与短剧用户心理研究专家。必须输出纯JSON对象，禁止编造传统影视明星。",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=8000,
        )

        logger.info("DeepSeek响应: %s...", response[:500])
        return self._parse_response(response)

    def _normalize_rankings(self, rankings: List[Any]) -> List[Dict[str, Any]]:
        """将 Pydantic 对象或字典统一转换为字典列表。"""
        result: List[Dict[str, Any]] = []
        for item in rankings:
            if hasattr(item, "model_dump"):
                result.append(item.model_dump())
            elif isinstance(item, dict):
                result.append(item)
        return result

    def _build_prompt(
        self,
        rankings_json_list: List[Dict[str, Any]],
        search_context: str,
        data_date: str,
    ) -> str:
        """构造 DeepSeek user prompt。"""
        return f"""【数据日期】：{data_date}
【基础榜单数据】：
{json.dumps(rankings_json_list, ensure_ascii=False, indent=2)}

🚨 真实互联网检索资料（从中提取，无提及则填'未知'）：
{search_context}

🚨【演员推理补充规则】：
- 若搜索结果无演员信息，请根据剧目类型（女频/男频）推理可能的演员特征
- 女频短剧主演通常是新生代女演员，优先选择：徐艺真、马秋元、王艺瑾、白妍、赵佳、余茵、杨咩咩、滕泽文、贾翼瑄、张楚嫣
- 男频短剧主演通常是新生代男演员，优先选择：曾辉、何健麒、孙晨越、王道铁、甄永涛、刘擎、张集骏、刘萧旭、鹿单东、龚俊
- 严禁填"未知"！如果实在不确定，请从上述名单中选择最可能的演员
- 必须填写具体的演员名字，不要出现"未知"

🚨【趋势标签判定规则】：
- 请根据检索到的资料，判断该剧的爆发速度。
- 如果该剧是刚刚上线几天就冲入榜单，或者新闻中明确提到其播放量增速极快、成为黑马，请将该剧的 `trend_tag` 字段赋值为 "🔥 飙升" 或 "🚀 新晋"。
- 如果只是老剧平稳表现，该字段请保留为空字符串 ""。

请补全缺失字段并输出纯JSON对象，不要加```json包裹。结构必须为：
{{
  "rankings": [
    {{
      "rank": 1,
      "title": "剧名",
      "female_lead": "女演员",
      "male_lead": "男演员",
      "views": "播放量",
      "views_num": 0,
      "platform": "平台",
      "genre": "题材",
      "tags": ["标签"],
      "trend": "趋势",
      "trend_tag": "",
      "trend_type": "new/up/down/same",
      "category": "female/male/ai",
      "is_ai": false,
      "desc": "剧情描述",
      "production_house": "制作厂牌",
      "core_trope": ["核心爽点"],
      "episodes_count": 80
    }}
  ]
}}"""

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        """健壮性解析 DeepSeek 返回的 JSON。"""
        try:
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            json_match = re.search(r'\{{[\s\S]*\}}', clean_response)
            if not json_match:
                json_match = re.search(r'\[[\s\S]*\]', clean_response)
            if not json_match:
                raise ValueError("未找到有效JSON对象或数组")

            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return parsed.get("rankings") or parsed.get("data") or []

        except Exception as parse_error:
            logger.error("enrich_node: JSON解析失败: %s", parse_error)
            logger.error("原始响应: %s", response)

        return []
