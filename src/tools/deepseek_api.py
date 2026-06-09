"""
DeepSeek API 工具类
支持普通对话和联网搜索
"""
import os
import json
import logging
import requests
from typing import List, Dict, Any, Optional, Iterator

logger = logging.getLogger(__name__)

# DeepSeek API 配置 - 支持从环境变量或.env文件加载
def _load_api_key() -> str:
    """加载API密钥，优先从环境变量，其次从.env文件"""
    # 优先从环境变量读取
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if api_key:
        return api_key
    
    # 尝试从.env文件读取
    env_paths = [
        os.path.join(os.getenv("COZE_WORKSPACE_PATH", ""), ".env"),
        ".env",
        "/workspace/projects/.env"
    ]
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DEEPSEEK_API_KEY="):
                            return line.split("=", 1)[1].strip()
            except Exception as e:
                logger.warning(f"读取.env文件失败: {e}")
    
    return ""

DEEPSEEK_API_KEY = _load_api_key()
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_URL = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"


class DeepSeekClient:
    """DeepSeek API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False
    ) -> str:
        """
        普通对话
        
        Args:
            messages: 消息列表，格式 [{"role": "system/user/assistant", "content": "..."}]
            model: 模型名称，默认 deepseek-chat
            temperature: 温度参数
            max_tokens: 最大输出token
            stream: 是否流式输出
        
        Returns:
            模型回复内容
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        try:
            response = requests.post(
                DEEPSEEK_CHAT_URL,
                headers=self.headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            logger.info(f"DeepSeek API调用成功，模型: {model}")
            return content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API调用失败: {e}")
            raise Exception(f"DeepSeek API调用失败: {e}")
    
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Iterator[str]:
        """
        流式对话
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出token
        
        Yields:
            流式输出的文本片段
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        
        try:
            response = requests.post(
                DEEPSEEK_CHAT_URL,
                headers=self.headers,
                json=payload,
                timeout=60,
                stream=True
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
            
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek流式调用失败: {e}")
            raise Exception(f"DeepSeek流式调用失败: {e}")
    
    def search(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 8192
    ) -> str:
        """
        联网搜索（DeepSeek内置搜索能力）
        
        DeepSeek的deepseek-chat模型具备联网搜索能力，
        会自动搜索互联网获取最新信息
        
        Args:
            query: 搜索查询
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大输出token
        
        Returns:
            搜索结果（包含搜索到的信息和模型回复）
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 添加搜索提示
        search_query = f"""请搜索互联网获取以下信息，并返回详细结果：

{query}

要求：
1. 优先搜索最新的公开数据源
2. 返回具体的数据内容，不要只是总结
3. 如果找到多个来源，整合后返回完整信息
4. 标注信息来源（如果有）
"""
        
        messages.append({"role": "user", "content": search_query})
        
        return self.chat(
            messages=messages,
            model="deepseek-chat",
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def search_json(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 8192
    ) -> Dict[str, Any]:
        """
        联网搜索并返回JSON格式结果
        
        Args:
            query: 搜索查询
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大输出token
        
        Returns:
            JSON格式的搜索结果
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        search_query = f"""请搜索互联网获取以下信息，并以JSON格式返回结果：

{query}

要求：
1. 搜索最新的公开数据源
2. 返回具体的数值和事实
3. 以JSON格式输出，不要包含Markdown代码块标记
4. 确保JSON格式正确可解析
"""
        
        messages.append({"role": "user", "content": search_query})
        
        response_text = self.chat(
            messages=messages,
            model="deepseek-chat",
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # 尝试解析JSON
        try:
            # 清理可能的Markdown代码块
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # 尝试找到JSON内容
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                return json.loads(json_match.group())
            
            return json.loads(response_text)
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}, 原始响应: {response_text[:200]}...")
            return {"raw_response": response_text, "parse_error": str(e)}
    
    def structured_output(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        结构化输出（自动解析JSON）
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大输出token
        
        Returns:
            JSON格式的结果
        """
        response_text = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # 尝试解析JSON
        try:
            # 清理可能的Markdown代码块
            import re
            if "```json" in response_text:
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
                if json_match:
                    return json.loads(json_match.group(1))
            elif "```" in response_text:
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
                if json_match:
                    return json.loads(json_match.group(1))
            
            # 尝试直接解析
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                return json.loads(json_match.group())
            
            return {"raw_response": response_text}
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}")
            return {"raw_response": response_text, "parse_error": str(e)}


# 便捷函数
def deepseek_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096
) -> str:
    """快捷对话函数"""
    client = DeepSeekClient()
    return client.chat(messages=messages, temperature=temperature, max_tokens=max_tokens)


def deepseek_search(
    query: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3
) -> str:
    """快捷搜索函数"""
    client = DeepSeekClient()
    return client.search(query=query, system_prompt=system_prompt, temperature=temperature)


def deepseek_search_json(
    query: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3
) -> Dict[str, Any]:
    """快捷搜索JSON函数"""
    client = DeepSeekClient()
    return client.search_json(query=query, system_prompt=system_prompt, temperature=temperature)