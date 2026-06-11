"""
Kimi (Moonshot) API 客户端
使用 OpenAI SDK 标准格式，支持联网搜索、对话和稳健 JSON 抽取。
"""
import ast
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Type

from openai import OpenAI

logger = logging.getLogger(__name__)


class MoonshotClient:
    """Kimi (Moonshot) API 客户端"""
    
    def __init__(self):
        """初始化客户端"""
        self.api_key = os.getenv("MOONSHOT_API_KEY", "")
        if not self.api_key:
            logger.warning("MOONSHOT_API_KEY 未设置，请检查环境变量")
        
        self.client = OpenAI(
            api_key=self.api_key or "missing-moonshot-api-key",
            # 国内 Moonshot/Kimi 控制台常用 .cn 域名；可用 MOONSHOT_BASE_URL 覆盖到 .ai 或私有网关。
            base_url=os.getenv("MOONSHOT_BASE_URL") or "https://api.moonshot.cn/v1"
        )
        self.model = os.getenv("MOONSHOT_MODEL", "moonshot-v1-32k")
        self.search_model = os.getenv("MOONSHOT_SEARCH_MODEL", self.model)
        self.web_search_tools = [
            {
                "type": "builtin_function",
                "function": {
                    "name": "$web_search",
                },
            }
        ]

    def _ensure_api_key(self) -> None:
        if not self.api_key:
            raise ValueError("MOONSHOT_API_KEY 未设置，无法调用 Kimi (Moonshot) API")
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> str:
        """
        对话接口
        
        Args:
            messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大输出tokens
            
        Returns:
            模型回复内容
        """
        try:
            self._ensure_api_key()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            content = response.choices[0].message.content or ""
            logger.info(f"Kimi chat 成功，返回 {len(content)} 字符")
            return content
        except Exception as e:
            logger.error(f"Kimi chat 失败: {e}")
            raise

    def structured_output(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        expected_type: Optional[Type[Any]] = None
    ) -> Any:
        """
        对话并解析结构化 JSON 输出。

        Kimi 经常会返回无 Markdown 包裹、带说明文字、单引号字面量或尾随逗号的内容。
        这里统一使用强健解析；解析失败时会打印完整 raw_text 并抛错，避免静默失败。
        """
        raw_text = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return self.extract_json(raw_text, expected_type=expected_type)
    
    def search(
        self,
        query: str,
        max_results: int = 5
    ) -> str:
        """
        联网搜索接口
        
        Kimi 内置联网搜索能力，会自动搜索互联网并返回带来源的回复
        
        Args:
            query: 搜索查询
            max_results: 期望的结果数量
            
        Returns:
            搜索结果文本（含来源引用）
        """
        # Kimi 官方联网搜索必须通过 builtin_function.$web_search tool 触发。
        search_prompt = f"""你必须进行联网搜索，提取最新的国内短剧行业网页、微信公众号或知乎文章的客观数据。
搜索查询：{query}

请返回以下格式：
【来源1】
标题: xxx
摘要: xxx  
链接: xxx

【来源2】
...

如果没有找到相关结果，请如实说明。"""
        
        try:
            self._ensure_api_key()
            content = self._chat_with_web_search(
                messages=[
                    {"role": "system", "content": "你是专业的信息检索助手，擅长搜索国内短剧行业的最新数据和动态。你必须联网搜索并返回客观事实。"},
                    {"role": "user", "content": search_prompt}
                ],
                temperature=0.3,
                max_tokens=3000
            )
            logger.info(f"Kimi 搜索成功，返回 {len(content)} 字符")
            return content
        except Exception as e:
            logger.error(f"Kimi 搜索失败: {e}")
            raise

    def search_json(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 3000,
        expected_type: Optional[Type[Any]] = dict
    ) -> Any:
        """
        联网搜索并解析 JSON。

        解析失败时强制 logger.error 输出 Kimi raw_text，调用方应捕获异常并写入 error_message。
        """
        prompt = f"""请联网搜索并提取以下信息，最后只输出 JSON，不要省略字段。

查询：{query}

如果某字段找不到，请使用"未知"或合理的空数组，不要编造具体事实。"""
        raw_text = self._chat_with_web_search(
            messages=[
                {"role": "system", "content": system_prompt or "你是严谨的数据检索和结构化抽取助手。"},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return self.extract_json(raw_text, expected_type=expected_type)
    
    def structured_search(
        self,
        query: str,
        extract_fields: List[str]
    ) -> Dict[str, Any]:
        """
        结构化搜索 - 搜索并提取指定字段
        
        Args:
            query: 搜索查询
            extract_fields: 需要提取的字段列表
            
        Returns:
            结构化结果字典
        """
        extract_prompt = f"""搜索并提取以下信息：
查询：{query}

需要提取的字段：{', '.join(extract_fields)}

请以JSON格式返回，例如：
{{"field1": "value1", "field2": "value2"}}

如果某字段无法找到，填写"未知"。"""
        
        try:
            result = self.search_json(
                query=extract_prompt,
                system_prompt="你是数据提取专家，擅长从互联网搜索并提取结构化信息。你必须联网搜索并返回准确的JSON格式数据。",
                temperature=0.1,
                max_tokens=2000,
                expected_type=dict
            )
            logger.info(f"Kimi 结构化搜索成功")
            return result
        except Exception as e:
            logger.error(f"Kimi 结构化搜索失败: {e}")
            return {}

    def _chat_with_web_search(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 3000,
        max_rounds: int = 4
    ) -> str:
        """
        使用 Moonshot 官方 builtin_function.$web_search 完成联网搜索。

        官方约定：当 finish_reason == tool_calls 时，把 $web_search 的 arguments
        原样作为 role=tool 消息返回给模型，Kimi 会在下一轮生成包含搜索结果的回答。
        """
        self._ensure_api_key()
        working_messages: List[Dict[str, Any]] = list(messages)
        finish_reason: Optional[str] = None
        last_content = ""

        for _ in range(max_rounds):
            completion = self.client.chat.completions.create(
                model=self.search_model,
                messages=working_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=self.web_search_tools,
                # Kimi 官方要求使用 $web_search 时关闭 thinking。
                extra_body={"thinking": {"type": "disabled"}}
            )
            choice = completion.choices[0]
            message = choice.message
            finish_reason = choice.finish_reason
            last_content = message.content or ""

            if finish_reason == "tool_calls" and message.tool_calls:
                if hasattr(message, "model_dump"):
                    assistant_message = message.model_dump(exclude_none=True)
                else:
                    assistant_message = {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": message.tool_calls,
                    }
                working_messages.append(assistant_message)

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    raw_arguments = tool_call.function.arguments or "{}"
                    try:
                        tool_arguments = json.loads(raw_arguments)
                    except json.JSONDecodeError:
                        logger.error("Kimi $web_search arguments 不是合法 JSON，raw_arguments=%s", raw_arguments)
                        tool_arguments = {"raw_arguments": raw_arguments}

                    if tool_name == "$web_search":
                        tool_result: Any = tool_arguments
                    else:
                        tool_result = {"error": f"unknown tool: {tool_name}", "arguments": tool_arguments}

                    working_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })
                continue

            return last_content

        raise RuntimeError(f"Kimi web search 未在 {max_rounds} 轮内完成，最后 finish_reason={finish_reason}，last_content={last_content[:500]}")

    def extract_json(self, raw_text: str, expected_type: Optional[Type[Any]] = None) -> Any:
        """
        从 Kimi raw_text 中提取 JSON / Python 字面量。

        支持：
        - 纯 JSON
        - ```json fenced code
        - 前后有说明文字的 JSON 对象/数组
        - 单引号、True/False/None 等 Python literal 风格
        - 尾随逗号
        """
        candidates = self._json_candidates(raw_text)
        errors: List[str] = []

        for candidate in candidates:
            for parser_name, parser in (
                ("json", self._parse_json_candidate),
                ("literal_eval", self._parse_literal_candidate),
            ):
                try:
                    parsed = parser(candidate)
                    if expected_type is not None and not isinstance(parsed, expected_type):
                        errors.append(f"{parser_name}: expected {expected_type}, got {type(parsed)}")
                        continue
                    return parsed
                except Exception as exc:
                    errors.append(f"{parser_name}: {exc}")

        logger.error(
            "Kimi JSON解析失败，raw_text如下：\n%s\n解析错误：%s",
            raw_text,
            " | ".join(errors[-10:])
        )
        raise ValueError("无法从 Kimi 返回中解析 JSON")

    def _json_candidates(self, raw_text: str) -> List[str]:
        text = (raw_text or "").strip().lstrip("\ufeff")
        candidates: List[str] = []

        if text:
            candidates.append(text)

        fenced_blocks = re.findall(r"```(?:json|JSON|javascript|js|python|py)?\s*([\s\S]*?)\s*```", text)
        candidates.extend(block.strip() for block in fenced_blocks if block.strip())

        decoder = json.JSONDecoder()
        for idx, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                _, end = decoder.raw_decode(text[idx:])
                candidates.append(text[idx:idx + end].strip())
            except json.JSONDecodeError:
                continue

        candidates.extend(self._balanced_json_like_substrings(text))

        # 去重但保序
        seen = set()
        unique: List[str] = []
        for candidate in candidates:
            normalized = candidate.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def _balanced_json_like_substrings(self, text: str) -> List[str]:
        results: List[str] = []
        pairs = {"{": "}", "[": "]"}

        for start, open_char in enumerate(text):
            if open_char not in pairs:
                continue

            close_char = pairs[open_char]
            depth = 0
            in_string = False
            string_quote = ""
            escape = False

            for pos in range(start, len(text)):
                ch = text[pos]

                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == string_quote:
                        in_string = False
                    continue

                if ch in ("\"", "'"):
                    in_string = True
                    string_quote = ch
                    continue

                if ch == open_char:
                    depth += 1
                elif ch == close_char:
                    depth -= 1
                    if depth == 0:
                        results.append(text[start:pos + 1].strip())
                        break

        return results

    def _parse_json_candidate(self, candidate: str) -> Any:
        cleaned = self._clean_json_candidate(candidate)
        return json.loads(cleaned)

    def _parse_literal_candidate(self, candidate: str) -> Any:
        cleaned = self._clean_json_candidate(candidate)
        return ast.literal_eval(cleaned)

    def _clean_json_candidate(self, candidate: str) -> str:
        cleaned = candidate.strip().lstrip("\ufeff")
        cleaned = cleaned.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return cleaned