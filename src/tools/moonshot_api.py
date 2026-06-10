"""
Kimi (Moonshot) API 客户端
使用 OpenAI SDK 标准格式，支持联网搜索和对话
"""
import os
import logging
from typing import List, Dict, Any, Optional
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
            api_key=self.api_key,
            base_url="https://api.moonshot.cn/v1"
        )
        self.model = "moonshot-v1-32k"
    
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            content = response.choices[0].message.content
            logger.info(f"Kimi chat 成功，返回 {len(content)} 字符")
            return content
        except Exception as e:
            logger.error(f"Kimi chat 失败: {e}")
            raise
    
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
        # Kimi 的联网搜索通过特殊的 system prompt 触发
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是专业的信息检索助手，擅长搜索国内短剧行业的最新数据和动态。你必须联网搜索并返回客观事实。"},
                    {"role": "user", "content": search_prompt}
                ],
                temperature=0.3,  # 低温度保证事实准确性
                max_tokens=3000
            )
            content = response.choices[0].message.content
            logger.info(f"Kimi 搜索成功，返回 {len(content)} 字符")
            return content
        except Exception as e:
            logger.error(f"Kimi 搜索失败: {e}")
            raise
    
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是数据提取专家，擅长从互联网搜索并提取结构化信息。你必须联网搜索并返回准确的JSON格式数据。"},
                    {"role": "user", "content": extract_prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            content = response.choices[0].message.content
            
            # 尝试解析JSON
            import json
            # 清理可能的markdown包裹
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            logger.info(f"Kimi 结构化搜索成功")
            return result
        except Exception as e:
            logger.error(f"Kimi 结构化搜索失败: {e}")
            return {}