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

🚨 真实互联网检索资料（从中提取，无提及则留空）：
{search_context}

🚨【演员补充规则 - 反幻觉】：
- 仅当检索资料中明确出现演员姓名时，才填写 female_lead / male_lead。
- 检索无演员信息时，必须留空字符串 ""，禁止编造、禁止使用「李十三」「王十四」等编号式假名。
- 禁止使用传统影视明星（刘亦菲、杨幂、胡歌等）填补。
- 禁止从常见演员名单里「猜测」主演。

🚨【厂牌补充规则 - 反幻觉】：
- 仅当检索资料中明确出现制作公司/工作室/出品方时，才填写 production_house。
- 无信源时留空 ""，禁止编造「蓝海影视工作室」等模板化厂牌。
- 可识别的真实厂牌示例：九州、点众、麦芽、蜜糖、容量、天桥、花生、映客、番茄、网易。

🚨【热度字段规则】：
- weekly_heat_index：使用基础榜单中的周热播指数（weekly_index），禁止改写为播放量。
- views / views_num 与 weekly_heat_index 保持一致，均为周热播指数，单位不是播放量。
- total_index 为累计热播指数，禁止与周指数混淆。

🚨【元数据保留规则】：
- 基础榜单中已提供的 `series_id`、`cover`、`weekly_index`、`total_index` 必须原样保留。

🚨【趋势标签判定规则】：
- 新剧或明确黑马报道时，trend_tag 可为 "🔥 飙升" 或 "🚀 新晋"，否则留空。

请补全缺失字段并输出纯JSON对象，不要加```json包裹。结构必须为：
{{
  "rankings": [
    {{
      "rank": 1,
      "title": "剧名",
      "female_lead": "",
      "male_lead": "",
      "views": "周热播指数数字字符串",
      "views_num": 0,
      "weekly_heat_index": 0,
      "platform": "平台",
      "genre": "题材",
      "tags": ["标签"],
      "trend": "趋势",
      "trend_tag": "",
      "trend_type": "new/up/down/same",
      "category": "female/male/ai",
      "is_ai": false,
      "desc": "剧情描述",
      "production_house": "",
      "core_trope": ["核心爽点"],
      "episodes_count": 0,
      "series_id": "红果series_id",
      "cover": "封面URL",
      "total_index": 0
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
