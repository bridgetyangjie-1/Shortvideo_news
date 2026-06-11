"""
DeepSeek API 工具类
用于数据推理层 - 根据输入文本生成JSON输出
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from openai import OpenAI

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """DeepSeek API客户端 - 用于数据推理"""
    
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY未设置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = "deepseek-chat"
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4000
    ) -> str:
        """
        调用DeepSeek chat接口生成响应
        
        Args:
            messages: 消息列表 [{"role": "system/user", "content": "..."}]
            temperature: 温度参数，默认0.3（稳定输出）
            max_tokens: 最大token数
        
        Returns:
            响应文本
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            content = response.choices[0].message.content
            logger.info(f"DeepSeek响应成功，长度: {len(content)}")
            return content
        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {e}")
            raise